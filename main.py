import datetime as dt
import json
import threading
import time
from dataclasses import dataclass
from typing import Any, List

import cv2

from communication.cloud_sync import CloudSyncClient
from communication.socket_client import PersistentSocketClient
from config import Settings, load_settings
from detection.yolo_detector import YoloTrafficDetector
from logic.accident_ml import AccidentDetector
from logic.traffic_scheduler import ScheduleResult, TrafficScheduler
from utils.logger import build_logger


ACCIDENT_CONFIRM_FRAMES = 3
ACCIDENT_LOCK_DURATION = 10.0


def build_signal_json(
    mode: str,
    reason: str,
    lane_order: list[int],
    green_times: list[int],
    yellow_times: list[int],
    vehicle_counts: list[int],
    ambulance_active: bool,
    ambulance_lane: int | None,
    accident_active: bool,
    accident_lane: int | None,
    accident_confidence: float,
) -> dict[str, Any]:
    lanes = []
    for lane, green, yellow in zip(lane_order, green_times, yellow_times):
        count = vehicle_counts[lane - 1] if 0 <= lane - 1 < len(vehicle_counts) else 0
        lanes.append(
            {
                "lane": lane,
                "green": int(green),
                "yellow": int(yellow),
                "vehicle_count": int(count),
            }
        )

    return {
        "mode": mode,
        "reason": reason,
        "lanes": lanes,
        "ambulance": {
            "active": ambulance_active,
            "lane": ambulance_lane,
        },
        "accident": {
            "active": accident_active,
            "lane": accident_lane,
            "confidence": float(accident_confidence),
        },
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def build_interval_signal_json(
    mode: str,
    reason: str,
    active_lane: int,
    green_time: int,
    ambulance_active: bool,
    ambulance_lane: int | None,
    accident_active: bool,
    accident_lane: int | None,
    accident_confidence: float,
) -> dict[str, Any]:
    return {
        "mode": mode,
        "reason": reason,
        "active_lane": int(active_lane),
        "green": int(green_time),
        "ambulance": {
            "active": ambulance_active,
            "lane": ambulance_lane,
        },
        "accident": {
            "active": accident_active,
            "lane": accident_lane,
            "confidence": float(accident_confidence),
        },
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


@dataclass
class CameraState:
    url: str
    cap: cv2.VideoCapture | None = None
    last_open_attempt: float = 0.0


class TrafficControllerApp:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.logger = build_logger()

        self.detector = YoloTrafficDetector(
            settings.model_path,
            device=settings.device,
            conf_threshold=settings.primary_conf_threshold,
        )
        self.accident_detector = AccidentDetector(
            model_path=settings.accident_model_path,
            conf_threshold=settings.accident_conf_threshold,
        )
        self.scheduler = TrafficScheduler(
            lane_count=len(settings.camera_urls),
            default_green_durations=settings.default_green_durations,
            default_yellow_durations=settings.default_yellow_durations,
            ambulance_confirm_seconds=settings.ambulance_confirm_seconds,
            density_override_threshold=settings.density_override_threshold,
            total_override_cycle_time=settings.total_override_cycle_time,
            ambulance_detection_threshold=settings.ambulance_detection_threshold,
            ambulance_miss_threshold=settings.ambulance_miss_threshold,
            fairness_wait_weight=settings.fairness_wait_weight,
            max_consecutive_priority_cycles=settings.max_consecutive_priority_cycles,
            override_min_green=settings.override_min_green_seconds,
            override_max_green=settings.override_max_green_seconds,
            emergency_green_seconds=settings.emergency_green_seconds,
        )
        self.socket_client: PersistentSocketClient | None = None
        if settings.enable_pi:
            self.socket_client = PersistentSocketClient(
                host=settings.pi_host,
                port=settings.pi_port,
                connect_timeout=settings.connect_timeout_seconds,
                send_timeout=settings.send_timeout_seconds,
                retry_seconds=settings.socket_retry_seconds,
                logger=self.logger,
            )
        else:
            self.logger.info("Raspberry Pi communication is disabled (ENABLE_PI=0)")
        self.cloud_sync = CloudSyncClient(
            enabled=settings.cloud_sync_enabled,
            api_url=settings.cloud_api_url,
            interval_seconds=settings.cloud_sync_interval_seconds,
            junction_id=settings.junction_id,
            request_timeout_seconds=settings.cloud_request_timeout_seconds,
            max_retries=settings.cloud_max_retries,
            retry_backoff_seconds=settings.cloud_retry_backoff_seconds,
            queue_size=settings.cloud_queue_size,
            logger=self.logger,
        )

        self.cameras: List[CameraState] = [CameraState(url=url) for url in settings.camera_urls]
        self.frame_counts: List[int] = [0] * len(self.cameras)

        # Temporal validation state (per lane) to suppress single-frame false positives.
        self.accident_counter: List[int] = [0] * len(self.cameras)
        self.accident_confirmed: List[bool] = [False] * len(self.cameras)

        # Debounce lock state keeps behavior stable once an accident is confirmed.
        self.accident_lock = False
        self.accident_lock_time = 0.0
        self.locked_accident_lane: int | None = None
        self.locked_accident_confidence = 0.0

        # Visualization state for each camera frame.
        self.latest_accident_boxes: List[list[tuple[int, int, int, int]]] = [[] for _ in self.cameras]
        self.latest_accident_confidence: List[float] = [0.0] * len(self.cameras)
        self.latest_vehicle_counts: List[int] = [0] * len(self.cameras)
        self.latest_ambulance_detected: List[bool] = [False] * len(self.cameras)

        self.accident_active = False
        self.accident_lane: int | None = None
        self.running = True
        self.lock = threading.Lock()

        self._last_logged_mode: str | None = None
        self._last_logged_active_lane: int | None = None
        self._last_logged_ambulance_active = False
        self._last_logged_ambulance_lane: int | None = None

        self._locked_normal_schedule: ScheduleResult | None = None
        self._normal_lock_until = 0.0

        self.logger.info(f"Primary model loaded on device: {self.detector.device}")
        self.logger.info(f"Control mode: {self.settings.control_mode}")

    def _update_accident_state(self, detected_accident_lanes: list[int], confidence: float) -> None:
        now = time.time()

        if self.accident_lock:
            if now - self.accident_lock_time < ACCIDENT_LOCK_DURATION:
                self.accident_active = True
                self.accident_lane = self.locked_accident_lane
                return

            # Lock expired: clear lock and allow fresh confirmation.
            self.accident_lock = False
            self.accident_lock_time = 0.0
            self.locked_accident_lane = None
            self.locked_accident_confidence = 0.0
            self.accident_counter = [0] * len(self.cameras)
            self.accident_confirmed = [False] * len(self.cameras)

        lane_votes: dict[int, int] = {}
        for lane in detected_accident_lanes:
            lane_votes[lane] = lane_votes.get(lane, 0) + 1

        for lane_id in range(1, len(self.cameras) + 1):
            lane_idx = lane_id - 1
            if lane_votes.get(lane_id, 0) > 0:
                self.accident_counter[lane_idx] += 1
                if self.accident_counter[lane_idx] >= ACCIDENT_CONFIRM_FRAMES:
                    self.accident_confirmed[lane_idx] = True
            else:
                self.accident_counter[lane_idx] = 0
                self.accident_confirmed[lane_idx] = False

        confirmed_lanes = [idx + 1 for idx, is_confirmed in enumerate(self.accident_confirmed) if is_confirmed]
        if not confirmed_lanes:
            self.accident_active = False
            self.accident_lane = None
            return

        selected_lane = max(
            confirmed_lanes,
            key=lambda lane_id: lane_votes.get(lane_id, 0),
        )

        self.accident_active = True
        self.accident_lane = selected_lane
        self.accident_lock = True
        self.accident_lock_time = now
        self.locked_accident_lane = selected_lane
        self.locked_accident_confidence = confidence

        self.logger.warning(f"🚨 Accident detected in lane {selected_lane} (confidence: {confidence:.2f})")

    def _draw_lane_dividers(self, frame: Any) -> None:
        lane_count = max(len(self.cameras), 1)
        lane_width = self.settings.frame_width / lane_count
        for divider_idx in range(1, lane_count):
            x = int(divider_idx * lane_width)
            cv2.line(frame, (x, 0), (x, self.settings.frame_height), (255, 255, 255), 1)

    def _draw_accident_overlay(self, frame: Any, camera_idx: int) -> None:
        for x1, y1, x2, y2 in self.latest_accident_boxes[camera_idx]:
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
            cv2.putText(frame, "ACCIDENT", (x1, max(20, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        if self.accident_active and self.accident_lane is not None:
            confidence = self.locked_accident_confidence if self.accident_lock else self.latest_accident_confidence[camera_idx]
            cv2.putText(frame, "ACCIDENT DETECTED", (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            cv2.putText(
                frame,
                f"Lane {self.accident_lane} ACTIVE (conf: {confidence:.2f})",
                (10, 150),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 165, 255),
                2,
            )

    def _draw_ambulance_overlay(self, frame: Any, camera_idx: int) -> None:
        if self.latest_ambulance_detected[camera_idx]:
            cv2.putText(
                frame,
                "AMBULANCE DETECTED",
                (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 0, 0),
                2,
            )

    def _apply_stale_decay(self, lane_index: int) -> None:
        current = self.latest_vehicle_counts[lane_index]
        decayed_count = int(round(current * self.settings.stale_decay_factor))
        decayed_count = max(0, decayed_count)

        self.latest_vehicle_counts[lane_index] = decayed_count
        self.latest_ambulance_detected[lane_index] = False
        self.scheduler.update_lane_detection(
            lane_index=lane_index,
            vehicle_count=decayed_count,
            ambulance_detected=False,
        )

    @staticmethod
    def _resolve_active_lane(signal_json: dict[str, Any]) -> int | None:
        if signal_json.get("active_lane") is not None:
            return int(signal_json["active_lane"])

        lanes = signal_json.get("lanes")
        if isinstance(lanes, list) and lanes:
            first = lanes[0]
            if isinstance(first, dict) and first.get("lane") is not None:
                return int(first["lane"])

        return None

    def _log_signal_event(self, signal_json: dict[str, Any]) -> None:
        if self.settings.full_signal_logging:
            self.logger.info(f"Signal JSON: {json.dumps(signal_json)}")
            return

        mode = str(signal_json.get("mode", "UNKNOWN"))
        reason = str(signal_json.get("reason", "unknown"))
        active_lane = self._resolve_active_lane(signal_json)

        ambulance = signal_json.get("ambulance")
        if isinstance(ambulance, dict):
            ambulance_active = bool(ambulance.get("active", False))
            ambulance_lane = ambulance.get("lane")
        else:
            ambulance_active = False
            ambulance_lane = None

        changed = (
            mode != self._last_logged_mode
            or active_lane != self._last_logged_active_lane
            or ambulance_active != self._last_logged_ambulance_active
            or (ambulance_active and ambulance_lane != self._last_logged_ambulance_lane)
        )

        if changed:
            self.logger.info(
                "Signal update: "
                f"mode={mode}, reason={reason}, active_lane={active_lane}, "
                f"ambulance_active={ambulance_active}, ambulance_lane={ambulance_lane}"
            )

        if ambulance_active and (
            not self._last_logged_ambulance_active
            or ambulance_lane != self._last_logged_ambulance_lane
        ):
            self.logger.warning(f"Ambulance priority active on lane {ambulance_lane}")

        self._last_logged_mode = mode
        self._last_logged_active_lane = active_lane
        self._last_logged_ambulance_active = ambulance_active
        self._last_logged_ambulance_lane = ambulance_lane

    def _ensure_camera_open(self, idx: int) -> bool:
        cam = self.cameras[idx]
        now = time.time()

        if cam.cap is not None and cam.cap.isOpened():
            return True

        if now - cam.last_open_attempt < self.settings.camera_retry_seconds:
            return False

        cam.last_open_attempt = now
        if cam.cap is not None:
            cam.cap.release()
            cam.cap = None

        cap = cv2.VideoCapture(cam.url)
        if not cap.isOpened():
            self.logger.warning(f"Lane {idx + 1}: camera open failed ({cam.url})")
            return False

        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        cam.cap = cap
        self.logger.info(f"Lane {idx + 1}: camera connected")
        return True

    def _capture_loop(self) -> None:
        while self.running:
            with self.lock:
                for idx, _ in enumerate(self.cameras):
                    if not self._ensure_camera_open(idx):
                        self._apply_stale_decay(idx)
                        continue

                    cap = self.cameras[idx].cap
                    assert cap is not None

                    ok, frame = cap.read()
                    if not ok:
                        self.logger.warning(f"Lane {idx + 1}: frame read failed, reconnecting")
                        cap.release()
                        self.cameras[idx].cap = None
                        self._apply_stale_decay(idx)
                        continue

                    frame = cv2.resize(frame, (self.settings.frame_width, self.settings.frame_height))
                    self.frame_counts[idx] += 1

                    should_run_primary = (
                        self.frame_counts[idx] == 1
                        or self.frame_counts[idx] % self.settings.frame_skip == 0
                    )

                    result = None
                    if should_run_primary:
                        try:
                            result = self.detector.analyze_frame(frame)
                        except Exception as exc:
                            self.logger.exception(f"Lane {idx + 1}: inference error: {exc}")
                            self._apply_stale_decay(idx)
                            continue

                        self.latest_vehicle_counts[idx] = result.vehicle_count
                        self.latest_ambulance_detected[idx] = result.ambulance_detected

                        confirmed_lane = self.scheduler.update_lane_detection(
                            lane_index=idx,
                            vehicle_count=result.vehicle_count,
                            ambulance_detected=result.ambulance_detected,
                        )

                        if confirmed_lane is not None:
                            self.logger.warning(f"Ambulance confirmed in lane {confirmed_lane}")
                            if self.socket_client is not None:
                                self.socket_client.send_with_retry(f"AMBULANCE:LANE{confirmed_lane}")

                    # Run accident detection every N frames to keep inference lightweight.
                    if self.frame_counts[idx] % self.settings.accident_frame_skip == 0:
                        detected_accident_lanes: list[int] = []
                        try:
                            small_frame = cv2.resize(frame, (320, 320))
                            accident_data = self.accident_detector.detect(small_frame)

                            if accident_data["accident"]:
                                scale_x = self.settings.frame_width / 320.0
                                scale_y = self.settings.frame_height / 320.0
                                scaled_boxes: list[tuple[int, int, int, int]] = []
                                for x1, y1, x2, y2 in accident_data["boxes"]:
                                    scaled_boxes.append(
                                        (
                                            int(x1 * scale_x),
                                            int(y1 * scale_y),
                                            int(x2 * scale_x),
                                            int(y2 * scale_y),
                                        )
                                    )

                                detected_accident_lanes = [idx + 1] * len(scaled_boxes)
                                self.latest_accident_boxes[idx] = scaled_boxes
                                self.latest_accident_confidence[idx] = float(accident_data["confidence"])
                            else:
                                self.latest_accident_boxes[idx] = []
                                self.latest_accident_confidence[idx] = 0.0
                        except Exception as exc:
                            self.logger.exception(f"Lane {idx + 1}: accident detection failure: {exc}")
                            self.latest_accident_boxes[idx] = []
                            self.latest_accident_confidence[idx] = 0.0
                            detected_accident_lanes = []

                        # Temporal validation + debounce lock update.
                        confidence_for_state = self.latest_accident_confidence[idx] if detected_accident_lanes else 0.0
                        self._update_accident_state(
                            detected_accident_lanes=detected_accident_lanes,
                            confidence=confidence_for_state,
                        )

                    if self.settings.show_windows:
                        annotated = result.annotated_frame if result is not None else frame.copy()
                        cv2.putText(
                            annotated,
                            f"Lane {idx + 1}: {self.latest_vehicle_counts[idx]} vehicles",
                            (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.7,
                            (0, 255, 255),
                            2,
                        )
                        if self.accident_active and self.accident_lane is not None:
                            cv2.putText(
                                annotated,
                                f"ACCIDENT ALERT LANE {self.accident_lane}",
                                (10, 90),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.8,
                                (0, 165, 255),
                                2,
                            )

                        self._draw_lane_dividers(annotated)
                        self._draw_ambulance_overlay(annotated, idx)
                        self._draw_accident_overlay(annotated, idx)

                        cv2.imshow(f"Lane {idx + 1}", annotated)

            if self.settings.show_windows and cv2.waitKey(1) & 0xFF == ord("q"):
                self.running = False
                break

    def _should_preempt_cycle(self, schedule_mode: str, schedule_reason: str, first_lane: int | None) -> bool:
        with self.lock:
            if self.scheduler.ambulance_active:
                if schedule_reason != "ambulance":
                    return True
                if first_lane is None:
                    return True
                return self.scheduler.ambulance_lane != first_lane

            if schedule_mode == "OVERRIDE":
                return False

            return bool(self.scheduler.lane_counts) and (
                max(self.scheduler.lane_counts) > self.settings.density_override_threshold
            )

    def _sleep_cycle_window(
        self,
        planned_seconds: int,
        schedule_mode: str,
        schedule_reason: str,
        first_lane: int | None,
    ) -> bool:
        duration = max(planned_seconds, 1)
        tick = max(self.settings.cycle_sleep_tick_seconds, 0.05)
        end_time = time.time() + duration

        while self.running:
            remaining = end_time - time.time()
            if remaining <= 0:
                return False

            if self._should_preempt_cycle(schedule_mode, schedule_reason, first_lane):
                self.logger.info("Cycle preempted early due to urgent override condition")
                return True

            time.sleep(min(tick, remaining))

        return False

    def _select_cycle_schedule(self, now: float) -> ScheduleResult:
        with self.lock:
            if self.scheduler.ambulance_active:
                self._locked_normal_schedule = None
                self._normal_lock_until = 0.0
                return self.scheduler.next_cycle()

            if (
                self._locked_normal_schedule is not None
                and now < self._normal_lock_until
                and self._locked_normal_schedule.mode == "NORMAL"
            ):
                return self._locked_normal_schedule

            schedule = self.scheduler.next_cycle()
            if schedule.mode == "NORMAL" and self.settings.normal_decision_lock_seconds > 0:
                self._locked_normal_schedule = schedule
                self._normal_lock_until = now + self.settings.normal_decision_lock_seconds
            else:
                self._locked_normal_schedule = None
                self._normal_lock_until = 0.0

            return schedule

    def run(self) -> None:
        self.logger.info("Starting traffic controller")
        capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        capture_thread.start()

        self.logger.info(
            f"Configured {len(self.cameras)} lane(s), PI endpoint {self.settings.pi_host}:{self.settings.pi_port}"
        )
        time.sleep(self.settings.initial_wait_seconds)

        control_mode = self.settings.control_mode if self.settings.control_mode in {"cycle", "interval"} else "cycle"
        next_interval_time = time.time()

        try:
            while self.running:
                if control_mode == "interval":
                    now = time.time()
                    if now < next_interval_time:
                        time.sleep(0.2)
                        continue

                    with self.lock:
                        decision = self.scheduler.get_interval_decision(
                            control_interval_seconds=self.settings.control_interval_seconds,
                            min_green_time=self.settings.min_green_time,
                            max_green_time=self.settings.max_green_time,
                        )
                        ambulance_lane = self.scheduler.ambulance_lane if self.scheduler.ambulance_active else None
                        accident_confidence = max(self.latest_accident_confidence) if self.latest_accident_confidence else 0.0
                        signal_json = build_interval_signal_json(
                            mode=decision.mode,
                            reason=decision.reason,
                            active_lane=decision.active_lane,
                            green_time=decision.green_time,
                            ambulance_active=self.scheduler.ambulance_active,
                            ambulance_lane=ambulance_lane,
                            accident_active=self.accident_active,
                            accident_lane=self.accident_lane,
                            accident_confidence=accident_confidence,
                        )

                    self._log_signal_event(signal_json)

                    if self.cloud_sync.should_sync():
                        self.cloud_sync.sync(signal_json)

                    if self.socket_client is not None:
                        pi_message = f"LANE{decision.active_lane}:{decision.green_time}:0"
                        sent = self.socket_client.send_with_retry(pi_message)
                        if not sent:
                            self.logger.error("Failed to send interval signal to Raspberry Pi")

                    next_interval_time = now + self.settings.control_interval_seconds
                    continue

                now = time.time()
                schedule = self._select_cycle_schedule(now)

                with self.lock:
                    vehicle_counts = self.latest_vehicle_counts[:]
                    ambulance_lane = self.scheduler.ambulance_lane if self.scheduler.ambulance_active else None
                    accident_confidence = max(self.latest_accident_confidence) if self.latest_accident_confidence else 0.0
                    signal_json = build_signal_json(
                        mode=schedule.mode,
                        reason=schedule.reason,
                        lane_order=schedule.lane_order,
                        green_times=schedule.green_times,
                        yellow_times=schedule.yellow_times,
                        vehicle_counts=vehicle_counts,
                        ambulance_active=self.scheduler.ambulance_active,
                        ambulance_lane=ambulance_lane,
                        accident_active=self.accident_active,
                        accident_lane=self.accident_lane,
                        accident_confidence=accident_confidence,
                    )

                self._log_signal_event(signal_json)

                if self.cloud_sync.should_sync():
                    self.cloud_sync.sync(signal_json)

                if self.socket_client is not None:
                    message = self.scheduler.to_wire_message(schedule)
                    sent = self.socket_client.send_with_retry(message)
                    if not sent:
                        self.logger.error("Failed to send signal plan to Raspberry Pi")

                preempted = self._sleep_cycle_window(
                    planned_seconds=self.scheduler.cycle_duration(schedule),
                    schedule_mode=schedule.mode,
                    schedule_reason=schedule.reason,
                    first_lane=schedule.lane_order[0] if schedule.lane_order else None,
                )

                if preempted:
                    self._locked_normal_schedule = None
                    self._normal_lock_until = 0.0

        except KeyboardInterrupt:
            self.logger.info("Stopping traffic controller")
        finally:
            self.running = False
            capture_thread.join(timeout=2)
            self._shutdown()

    def _shutdown(self) -> None:
        self.cloud_sync.close()

        if self.socket_client is not None:
            self.socket_client.close()

        for cam in self.cameras:
            if cam.cap is not None:
                cam.cap.release()
                cam.cap = None

        if self.settings.show_windows:
            cv2.destroyAllWindows()


def main() -> None:
    settings = load_settings()
    app = TrafficControllerApp(settings)
    app.run()


if __name__ == "__main__":
    main()
