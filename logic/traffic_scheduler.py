import time
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class LaneSignal:
    lane: int
    green_seconds: int
    yellow_seconds: int


class TrafficScheduler:
    def __init__(
        self,
        lane_count: int,
        green_durations: List[int],
        yellow_durations: List[int],
        ambulance_confirm_seconds: int,
    ):
        self.lane_count = lane_count
        self.green_durations = self._expand(green_durations, lane_count, 10)
        self.yellow_durations = self._expand(yellow_durations, lane_count, 5)
        self.ambulance_confirm_seconds = ambulance_confirm_seconds

        self.lane_counts = [0] * lane_count
        self.ambulance_detection_times = [0.0] * lane_count
        self.ambulance_active = False
        self.ambulance_lane: Optional[int] = None

    @staticmethod
    def _expand(source: List[int], target_size: int, fallback: int) -> List[int]:
        if not source:
            return [fallback] * target_size
        values = source[:target_size]
        if len(values) < target_size:
            values.extend([values[-1] if values else fallback] * (target_size - len(values)))
        return values

    def update_lane_detection(self, lane_index: int, vehicle_count: int, ambulance_detected: bool) -> Optional[int]:
        self.lane_counts[lane_index] = vehicle_count

        if ambulance_detected:
            if self.ambulance_detection_times[lane_index] == 0:
                self.ambulance_detection_times[lane_index] = time.time()
            elif (
                time.time() - self.ambulance_detection_times[lane_index] >= self.ambulance_confirm_seconds
                and not self.ambulance_active
            ):
                self.ambulance_active = True
                self.ambulance_lane = lane_index + 1
                return self.ambulance_lane
        else:
            self.ambulance_detection_times[lane_index] = 0
            if self.ambulance_active and self.ambulance_lane == lane_index + 1:
                self.ambulance_active = False
                self.ambulance_lane = None

        return None

    def _normal_priority(self) -> List[LaneSignal]:
        lane_order = sorted(
            enumerate(self.lane_counts, start=1),
            key=lambda x: x[1],
            reverse=True,
        )
        signals: List[LaneSignal] = []
        for rank, (lane, _) in enumerate(lane_order):
            signals.append(
                LaneSignal(
                    lane=lane,
                    green_seconds=self.green_durations[rank],
                    yellow_seconds=self.yellow_durations[rank],
                )
            )
        return signals

    def _accident_priority(self, accident_lane: int) -> List[LaneSignal]:
        normal_lanes: List[Tuple[int, int]] = [
            (idx + 1, count)
            for idx, count in enumerate(self.lane_counts)
            if (idx + 1) != accident_lane
        ]
        normal_lanes.sort(key=lambda x: x[1], reverse=True)

        order = [
            LaneSignal(
                lane=accident_lane,
                green_seconds=self.green_durations[0],
                yellow_seconds=self.yellow_durations[0],
            )
        ]

        for idx, (lane, _) in enumerate(normal_lanes, start=1):
            order.append(
                LaneSignal(
                    lane=lane,
                    green_seconds=self.green_durations[idx],
                    yellow_seconds=self.yellow_durations[idx],
                )
            )

        return order

    def next_cycle(self, accident_flag: bool = False, accident_lane: Optional[int] = None) -> List[LaneSignal]:
        if accident_flag and accident_lane is not None and 1 <= accident_lane <= self.lane_count:
            return self._accident_priority(accident_lane)

        if not self.ambulance_active or self.ambulance_lane is None:
            return self._normal_priority()

        normal_lanes: List[Tuple[int, int]] = [
            (idx + 1, count)
            for idx, count in enumerate(self.lane_counts)
            if (idx + 1) != self.ambulance_lane
        ]
        normal_lanes.sort(key=lambda x: x[1], reverse=True)

        order = [
            LaneSignal(
                lane=self.ambulance_lane,
                green_seconds=self.green_durations[0],
                yellow_seconds=self.yellow_durations[0],
            )
        ]

        for idx, (lane, _) in enumerate(normal_lanes, start=1):
            order.append(
                LaneSignal(
                    lane=lane,
                    green_seconds=self.green_durations[idx],
                    yellow_seconds=self.yellow_durations[idx],
                )
            )

        return order

    @staticmethod
    def to_wire_message(order: List[LaneSignal]) -> str:
        return ",".join(
            f"LANE{signal.lane}:{signal.green_seconds}:{signal.yellow_seconds}"
            for signal in order
        )

    @staticmethod
    def cycle_duration(order: List[LaneSignal]) -> int:
        return sum(signal.green_seconds + signal.yellow_seconds for signal in order)
