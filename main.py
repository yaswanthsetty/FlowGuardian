import threading
import time
from dataclasses import dataclass
from typing import Any, List

import cv2

from communication.cloud_sync import CloudSyncClient
from communication.socket_client import PersistentSocketClient
from config import Settings, load_settings
from detection.ambulance_detector import AmbulanceDetector
from detection.yolo_detector import YoloTrafficDetector
from logic.accident_ml import AccidentDetector
from logic.traffic_scheduler import TrafficScheduler
from utils.logger import build_logger


ACCIDENT_CONFIRM_FRAMES = 3
ACCIDENT_LOCK_DURATION = 10.0


def get_lane_from_bbox(bbox: tuple[int, int, int, int], frame_width: int, num_lanes: int) -> int:
    x1, _, x2, _ = bbox
    center_x = (x1 + x2) / 2.0
    lane_width = max(frame_width / max(num_lanes, 1), 1)
    lane_index = int(center_x / lane_width)
    lane_index = max(0, min(lane_index, num_lanes - 1))
    return lane_index + 1


@dataclass
class CameraState:
    url: str
    cap: cv2.VideoCapture | None = None
    last_open_attempt: float = 0.0


class TrafficControllerApp:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.logger = build_logger()

        self.detector = YoloTrafficDetector(settings.model_path)
        self.ambulance_detector = AmbulanceDetector(
            model_path=settings.ambulance_model_path,
            conf_threshold=settings.ambulance_conf_threshold,
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
        )
        self.socket_client = PersistentSocketClient(
            host=settings.pi_host,
            port=settings.pi_port,
            connect_timeout=settings.connect_timeout_seconds,
            send_timeout=settings.send_timeout_seconds,
            retry_seconds=settings.socket_retry_seconds,
            logger=self.logger,
        )
        self.cloud_sync = CloudSyncClient(
            enabled=settings.cloud_sync_enabled,
            api_url=settings.cloud_api_url,
            interval_seconds=settings.cloud_sync_interval_seconds,
            junction_id=settings.junction_id,
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
        self.latest_ambulance_boxes: List[list[tuple[int, int, int, int]]] = [[] for _ in self.cameras]
        self.latest_ambulance_confidence: List[float] = [0.0] * len(self.cameras)
        self.latest_ambulance_detected: List[bool] = [False] * len(self.cameras)

        self.accident_active = False
        self.accident_lane: int | None = None
        self.running = True
        self.lock = threading.Lock()

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
        for x1, y1, x2, y2 in self.latest_ambulance_boxes[camera_idx]:
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
            cv2.putText(frame, "AMBULANCE", (x1, max(20, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)

        if self.latest_ambulance_detected[camera_idx]:
            cv2.putText(
                frame,
                f"AMBULANCE CANDIDATE (conf: {self.latest_ambulance_confidence[camera_idx]:.2f})",
                (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 0, 0),
                2,
            )

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

        cam.cap = cap
        self.logger.info(f"Lane {idx + 1}: camera connected")
        return True

    def _capture_loop(self) -> None:
        while self.running:
            with self.lock:
                for idx, _ in enumerate(self.cameras):
                    if not self._ensure_camera_open(idx):
                        continue

                    cap = self.cameras[idx].cap
                    assert cap is not None

                    ok, frame = cap.read()
                    if not ok:
                        self.logger.warning(f"Lane {idx + 1}: frame read failed, reconnecting")
                        cap.release()
                        self.cameras[idx].cap = None
                        continue

                    frame = cv2.resize(frame, (self.settings.frame_width, self.settings.frame_height))
                    self.frame_counts[idx] += 1

                    try:
                        result = self.detector.analyze_frame(frame)
                    except Exception as exc:
                        self.logger.exception(f"Lane {idx + 1}: inference error: {exc}")
                        continue

                    ambulance_detected = self.latest_ambulance_detected[idx]
                    if self.frame_counts[idx] % self.settings.ambulance_frame_skip == 0:
                        try:
                            ambulance_data = self.ambulance_detector.detect(frame)
                            ambulance_detected = bool(ambulance_data["detected"])
                            self.latest_ambulance_detected[idx] = ambulance_detected
                            self.latest_ambulance_confidence[idx] = float(ambulance_data["confidence"])
                            self.latest_ambulance_boxes[idx] = ambulance_data["boxes"]
                        except Exception as exc:
                            self.logger.exception(f"Lane {idx + 1}: ambulance detection failure: {exc}")
                            ambulance_detected = False
                            self.latest_ambulance_detected[idx] = False
                            self.latest_ambulance_confidence[idx] = 0.0
                            self.latest_ambulance_boxes[idx] = []

                    confirmed_lane = self.scheduler.update_lane_detection(
                        lane_index=idx,
                        vehicle_count=result.vehicle_count,
                        ambulance_detected=ambulance_detected,
                    )
                    self.latest_vehicle_counts[idx] = result.vehicle_count

                    if confirmed_lane is not None:
                        self.logger.warning(f"Ambulance confirmed in lane {confirmed_lane}")
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

                                detected_accident_lanes = [
                                    get_lane_from_bbox(
                                        bbox=box,
                                        frame_width=self.settings.frame_width,
                                        num_lanes=len(self.cameras),
                                    )
                                    for box in scaled_boxes
                                ]
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
                        annotated = result.annotated_frame
                        cv2.putText(
                            annotated,
                            f"Lane {idx + 1}: {result.vehicle_count} vehicles",
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

    def run(self) -> None:
        self.logger.info("Starting traffic controller")
        capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        capture_thread.start()

        self.logger.info(
            f"Configured {len(self.cameras)} lane(s), PI endpoint {self.settings.pi_host}:{self.settings.pi_port}"
        )
        time.sleep(self.settings.initial_wait_seconds)

        try:
            while self.running:
                with self.lock:
                    schedule = self.scheduler.next_cycle()
                    message = self.scheduler.to_wire_message(schedule)
                    vehicle_counts = self.latest_vehicle_counts[:]
                    ambulance_lane = self.scheduler.ambulance_lane if self.scheduler.ambulance_active else None
                    accident_confidence = max(self.latest_accident_confidence) if self.latest_accident_confidence else 0.0

                if self.cloud_sync.should_sync():
                    payload = self.cloud_sync.build_payload(
                        mode=schedule.mode,
                        reason=schedule.reason,
                        lane_order=schedule.lane_order,
                        green_times=schedule.green_times,
                        yellow_times=schedule.yellow_times,
                        vehicle_counts=vehicle_counts,
                        ambulance_lane=ambulance_lane,
                        accident_active=self.accident_active,
                        accident_lane=self.accident_lane,
                        accident_confidence=accident_confidence,
                    )
                    self.cloud_sync.sync(payload)

                self.logger.info(f"Signal plan: {message}")
                sent = self.socket_client.send_with_retry(message)
                if not sent:
                    self.logger.error("Failed to send signal plan to Raspberry Pi")

                sleep_for = self.scheduler.cycle_duration(schedule)
                time.sleep(max(sleep_for, 1))

        except KeyboardInterrupt:
            self.logger.info("Stopping traffic controller")
        finally:
            self.running = False
            capture_thread.join(timeout=2)
            self._shutdown()

    def _shutdown(self) -> None:
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
