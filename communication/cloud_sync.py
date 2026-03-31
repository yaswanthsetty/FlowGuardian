from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import datetime as dt
import threading
import time
from typing import Any, Dict, List, Optional

import requests


@dataclass
class _QueuedPayload:
    payload: Dict[str, Any]
    retry_count: int = 0
    next_attempt_at: float = 0.0


class CloudSyncClient:
    def __init__(
        self,
        enabled: bool,
        api_url: str,
        interval_seconds: int,
        junction_id: str,
        request_timeout_seconds: float = 5.0,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.5,
        queue_size: int = 50,
        logger=None,
    ):
        self.enabled = enabled
        self.api_url = api_url
        self.interval_seconds = max(1, interval_seconds)
        self.junction_id = junction_id
        self.request_timeout_seconds = max(1.0, request_timeout_seconds)
        self.max_retries = max(0, max_retries)
        self.retry_backoff_seconds = max(0.1, retry_backoff_seconds)
        self.queue_size = max(1, queue_size)
        self.logger = logger
        self._last_sync_time = 0.0
        self._last_enqueue_time = 0.0
        self._session = requests.Session()

        self._queue: deque[_QueuedPayload] = deque()
        self._queue_lock = threading.Lock()
        self._queue_cv = threading.Condition(self._queue_lock)
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

        if self.enabled:
            self._start_worker()

    def _log(self, level: str, message: str) -> None:
        if self.logger is None:
            return
        getattr(self.logger, level)(message)

    def should_sync(self) -> bool:
        if not self.enabled:
            return False
        now = time.time()
        return (now - self._last_enqueue_time) >= self.interval_seconds

    def _start_worker(self) -> None:
        if self._worker_thread is not None and self._worker_thread.is_alive():
            return

        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._worker_loop, name="cloud-sync-worker", daemon=True)
        self._worker_thread.start()

    def _enqueue_item(self, item: _QueuedPayload) -> None:
        with self._queue_cv:
            if self._stop_event.is_set():
                self._log("warning", "Cloud worker stopping; dropping payload enqueue")
                return

            if len(self._queue) >= self.queue_size:
                dropped = self._queue.popleft()
                self._log(
                    "warning",
                    f"Cloud queue full ({self.queue_size}). Dropping oldest payload with retry_count={dropped.retry_count}",
                )

            self._queue.append(item)
            self._queue_cv.notify()

    def _send_once(self, payload: Dict[str, Any]) -> bool:
        response = self._session.post(
            self.api_url,
            json=payload,
            timeout=self.request_timeout_seconds,
        )
        response.raise_for_status()
        self._last_sync_time = time.time()
        self._log("info", f"Cloud sync success: {response.status_code}")
        return True

    def _worker_loop(self) -> None:
        while True:
            with self._queue_cv:
                while not self._queue and not self._stop_event.is_set():
                    self._queue_cv.wait(timeout=0.5)

                if self._stop_event.is_set() and not self._queue:
                    return

                item = self._queue[0]
                now = time.time()
                wait_seconds = item.next_attempt_at - now

                if wait_seconds > 0:
                    self._queue_cv.wait(timeout=min(wait_seconds, 0.5))
                    continue

                item = self._queue.popleft()

            try:
                self._send_once(item.payload)
            except requests.RequestException as exc:
                if self._stop_event.is_set():
                    self._log("warning", f"Cloud worker stopping during failed send: {exc}")
                    continue

                if item.retry_count >= self.max_retries:
                    self._log(
                        "warning",
                        f"Cloud sync dropped payload after {item.retry_count} retries: {exc}",
                    )
                    continue

                next_retry = item.retry_count + 1
                backoff = self.retry_backoff_seconds * (2 ** (next_retry - 1))
                item.retry_count = next_retry
                item.next_attempt_at = time.time() + backoff
                self._log(
                    "warning",
                    f"Cloud sync retry scheduled ({next_retry}/{self.max_retries}) in {backoff:.2f}s: {exc}",
                )
                self._enqueue_item(item)

    def build_payload(
        self,
        mode: str,
        reason: str,
        lane_order: List[int],
        green_times: List[int],
        yellow_times: List[int],
        vehicle_counts: List[int],
        ambulance_lane: Optional[int],
        accident_active: bool,
        accident_lane: Optional[int],
        accident_confidence: float,
    ) -> Dict[str, Any]:
        lanes = []
        lane_timing = {
            lane: (green, yellow)
            for lane, green, yellow in zip(lane_order, green_times, yellow_times)
        }

        for lane_id in sorted(lane_timing.keys()):
            green, yellow = lane_timing[lane_id]
            count = vehicle_counts[lane_id - 1] if 0 <= lane_id - 1 < len(vehicle_counts) else 0
            lanes.append(
                {
                    "lane": lane_id,
                    "green": int(green),
                    "yellow": int(yellow),
                    "vehicle_count": int(count),
                }
            )

        return {
            "mode": mode,
            "reason": reason,
            "junction_id": self.junction_id,
            "lane_order": lane_order,
            "lanes": lanes,
            "ambulance_lane": ambulance_lane,
            "accident_alert": {
                "active": accident_active,
                "lane": accident_lane,
                "confidence": float(accident_confidence),
            },
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        }

    def sync(self, payload: Dict[str, Any]) -> None:
        if not self.enabled:
            return
        if not self.api_url:
            self._log("warning", "Cloud sync enabled but CLOUD_API_URL is empty")
            return

        self._last_enqueue_time = time.time()
        self._start_worker()
        self._enqueue_item(
            _QueuedPayload(
                payload=payload,
                retry_count=0,
                next_attempt_at=self._last_enqueue_time,
            )
        )

    def close(self, timeout_seconds: float = 2.0) -> None:
        self._stop_event.set()
        with self._queue_cv:
            self._queue.clear()
            self._queue_cv.notify_all()

        if self._worker_thread is not None and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=max(0.1, timeout_seconds))

        self._session.close()
