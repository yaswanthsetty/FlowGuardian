from typing import Any, Dict, List, Tuple

from ultralytics import YOLO


class AmbulanceDetector:
    def __init__(self, model_path: str, conf_threshold: float = 0.5):
        self.model = YOLO(model_path)
        self.conf_threshold = conf_threshold

    @staticmethod
    def _label_for_id(names: Any, class_id: int) -> str:
        if isinstance(names, dict):
            return str(names.get(class_id, "")).lower()
        if isinstance(names, list) and 0 <= class_id < len(names):
            return str(names[class_id]).lower()
        return ""

    def detect(self, frame: Any) -> Dict[str, Any]:
        results = self.model(frame, verbose=False)

        boxes: List[Tuple[int, int, int, int]] = []
        best_confidence = 0.0

        for result in results:
            for box in result.boxes:
                class_id = int(box.cls[0])
                confidence = float(box.conf[0])
                class_name = self._label_for_id(self.model.names, class_id)

                if "ambulance" not in class_name:
                    continue
                if confidence < self.conf_threshold:
                    continue

                x1, y1, x2, y2 = box.xyxy[0].tolist()
                boxes.append((int(x1), int(y1), int(x2), int(y2)))
                if confidence > best_confidence:
                    best_confidence = confidence

        return {
            "detected": len(boxes) > 0,
            "confidence": best_confidence,
            "boxes": boxes,
        }
