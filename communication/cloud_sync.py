from __future__ import annotations

import datetime as dt
import time
from typing import Any, Dict, List, Optional

import requests


class CloudSyncClient:
    def __init__(
        self,
        enabled: bool,
        api_url: str,
        interval_seconds: int,
        junction_id: str,
        logger=None,
    ):
        self.enabled = enabled
        self.api_url = api_url
        self.interval_seconds = max(1, interval_seconds)
        self.junction_id = junction_id
        self.logger = logger
        self._last_sync_time = 0.0

    def _log(self, level: str, message: str) -> None:
        if self.logger is None:
            return
        getattr(self.logger, level)(message)

    def should_sync(self) -> bool:
        if not self.enabled:
            return False
        now = time.time()
        return (now - self._last_sync_time) >= self.interval_seconds

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

        try:
            response = requests.post(self.api_url, json=payload, timeout=5)
            response.raise_for_status()
            self._last_sync_time = time.time()
            self._log("info", f"Cloud sync success: {response.status_code}")
        except requests.RequestException as exc:
            self._log("warning", f"Cloud sync failed: {exc}")
