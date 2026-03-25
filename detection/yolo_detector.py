from dataclasses import dataclass
from typing import Any

from ultralytics import YOLO


@dataclass
class DetectionResult:
    vehicle_count: int
    ambulance_detected: bool
    annotated_frame: Any


class YoloTrafficDetector:
    def __init__(self, model_path: str):
        self.model = YOLO(model_path)

    def analyze_frame(self, frame: Any) -> DetectionResult:
        results = self.model(frame)
        rendered = results[0].plot()

        vehicle_count = 0
        ambulance_detected = False

        for box in results[0].boxes:
            cls_id = int(box.cls[0])
            label = str(self.model.names[cls_id]).lower()
            if any(token in label for token in ("car", "bus", "truck", "motorbike", "vehicle")):
                vehicle_count += 1
            elif "ambulance" in label:
                ambulance_detected = True

        return DetectionResult(
            vehicle_count=vehicle_count,
            ambulance_detected=ambulance_detected,
            annotated_frame=rendered,
        )
