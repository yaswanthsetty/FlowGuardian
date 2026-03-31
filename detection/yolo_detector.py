from dataclasses import dataclass
from typing import Any

import torch
from ultralytics import YOLO


@dataclass
class DetectionResult:
    vehicle_count: int
    ambulance_detected: bool
    annotated_frame: Any


class YoloTrafficDetector:
    def __init__(self, model_path: str, device: str = "auto", conf_threshold: float = 0.35):
        self.model = YOLO(model_path)
        self.conf_threshold = max(0.0, min(conf_threshold, 1.0))
        requested = (device or "auto").lower()
        if requested == "auto":
            self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        elif requested == "cuda" and torch.cuda.is_available():
            self.device = "cuda:0"
        elif requested.startswith("cuda") and torch.cuda.is_available():
            self.device = requested
        else:
            self.device = "cpu"

    def analyze_frame(self, frame: Any) -> DetectionResult:
        results = self.model.predict(frame, device=self.device, verbose=False)
        rendered = results[0].plot()

        vehicle_count = 0
        ambulance_detected = False

        vehicle_tokens = ("car", "bus", "truck", "motorbike", "motorcycle", "bike", "vehicle")

        boxes = results[0].boxes
        if boxes is not None:
            for box in boxes:
                confidence = float(box.conf[0])
                if confidence < self.conf_threshold:
                    continue
                cls_id = int(box.cls[0])
                label = str(self.model.names[cls_id]).lower()
                if "ambulance" in label:
                    ambulance_detected = True
                elif any(token in label for token in vehicle_tokens):
                    vehicle_count += 1

        return DetectionResult(
            vehicle_count=vehicle_count,
            ambulance_detected=ambulance_detected,
            annotated_frame=rendered,
        )
