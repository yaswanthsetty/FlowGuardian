import time
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class LaneSignal:
    lane: int
    green_seconds: int
    yellow_seconds: int


@dataclass
class ScheduleResult:
    mode: str
    lane_order: List[int]
    green_times: List[int]
    yellow_times: List[int]
    reason: str

    def as_lane_signals(self) -> List[LaneSignal]:
        return [
            LaneSignal(lane=lane, green_seconds=green, yellow_seconds=yellow)
            for lane, green, yellow in zip(self.lane_order, self.green_times, self.yellow_times)
        ]


@dataclass
class IntervalDecision:
    mode: str
    reason: str
    active_lane: int
    green_time: int


class TrafficScheduler:
    def __init__(
        self,
        lane_count: int,
        default_green_durations: List[int],
        default_yellow_durations: List[int],
        ambulance_confirm_seconds: int,
        density_override_threshold: int,
        total_override_cycle_time: int,
    ):
        self.lane_count = lane_count
        self.default_green_durations = self._expand(default_green_durations, lane_count, 20)
        self.default_yellow_durations = self._expand(default_yellow_durations, lane_count, 5)
        self.ambulance_confirm_seconds = ambulance_confirm_seconds
        self.density_override_threshold = density_override_threshold
        self.total_override_cycle_time = total_override_cycle_time
        self.min_override_green = 5

        self.lane_counts = [0] * lane_count
        self.ambulance_detection_times = [0.0] * lane_count
        self.ambulance_active = False
        self.ambulance_lane: Optional[int] = None
        self._normal_interval_index = 0

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

    def _normal_priority(self) -> ScheduleResult:
        lane_order = list(range(1, self.lane_count + 1))
        green_times = self.default_green_durations[:]
        yellow_times = self.default_yellow_durations[:]
        return ScheduleResult(
            mode="NORMAL",
            lane_order=lane_order,
            green_times=green_times,
            yellow_times=yellow_times,
            reason="default",
        )

    def _build_override_schedule(self, reason: str) -> ScheduleResult:
        prioritized_lanes: List[int] = []

        if self.ambulance_active and self.ambulance_lane is not None:
            prioritized_lanes.append(self.ambulance_lane)

        lane_order = sorted(
            enumerate(self.lane_counts, start=1),
            key=lambda x: x[1],
            reverse=True,
        )
        for lane, _ in lane_order:
            if lane not in prioritized_lanes:
                prioritized_lanes.append(lane)

        green_times = self._dynamic_green_times(prioritized_lanes)
        yellow_times = self.default_yellow_durations[:]

        return ScheduleResult(
            mode="OVERRIDE",
            lane_order=prioritized_lanes,
            green_times=green_times,
            yellow_times=yellow_times,
            reason=reason,
        )

    def _dynamic_green_times(self, lane_order: List[int]) -> List[int]:
        ordered_counts = [self.lane_counts[lane - 1] for lane in lane_order]
        total_count = max(sum(ordered_counts), 1)
        lane_total = len(lane_order)

        if self.total_override_cycle_time <= lane_total * self.min_override_green:
            return [self.min_override_green] * lane_total

        available = self.total_override_cycle_time - (lane_total * self.min_override_green)
        proportional_extras = [int((count / total_count) * available) for count in ordered_counts]
        extras_sum = sum(proportional_extras)

        # Distribute remaining seconds to the busiest lanes for stable totals.
        remaining = available - extras_sum
        busy_rank = sorted(range(lane_total), key=lambda idx: ordered_counts[idx], reverse=True)
        for idx in busy_rank:
            if remaining <= 0:
                break
            proportional_extras[idx] += 1
            remaining -= 1

        return [self.min_override_green + extra for extra in proportional_extras]

    def next_cycle(self) -> ScheduleResult:
        if self.ambulance_active and self.ambulance_lane is not None:
            return self._build_override_schedule(reason="ambulance")

        if max(self.lane_counts) > self.density_override_threshold:
            return self._build_override_schedule(reason="density")

        return self._normal_priority()

    def get_interval_decision(
        self,
        control_interval_seconds: int,
        min_green_time: int,
        max_green_time: int,
    ) -> IntervalDecision:
        schedule = self.next_cycle()

        bounded_green = max(min_green_time, min(control_interval_seconds, max_green_time))

        if not schedule.lane_order:
            active_lane = 1
        elif schedule.mode == "NORMAL":
            active_lane = schedule.lane_order[self._normal_interval_index % len(schedule.lane_order)]
            self._normal_interval_index += 1
        else:
            active_lane = schedule.lane_order[0]

        return IntervalDecision(
            mode=schedule.mode,
            reason=schedule.reason,
            active_lane=active_lane,
            green_time=bounded_green,
        )

    @staticmethod
    def to_wire_message(schedule: ScheduleResult) -> str:
        order = schedule.as_lane_signals()
        return ",".join(
            f"LANE{signal.lane}:{signal.green_seconds}:{signal.yellow_seconds}"
            for signal in order
        )

    @staticmethod
    def cycle_duration(schedule: ScheduleResult) -> int:
        return sum(green + yellow for green, yellow in zip(schedule.green_times, schedule.yellow_times))
