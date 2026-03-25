import argparse
from pathlib import Path

from ultralytics import YOLO


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a YOLO model for traffic/ambulance detection")
    parser.add_argument("--model", default="yolov8n.pt", help="Model checkpoint to start from")
    parser.add_argument("--data", default="data.yaml", help="Path to dataset YAML")
    parser.add_argument("--epochs", type=int, default=50, help="Number of training epochs")
    parser.add_argument("--imgsz", type=int, default=640, help="Image size")
    parser.add_argument("--batch", type=int, default=16, help="Batch size")
    parser.add_argument("--project", default="runs/detect", help="Output project directory")
    parser.add_argument("--name", default="train_refactored", help="Run name")
    parser.add_argument("--device", default=None, help="Device, for example cpu, 0, 0,1")
    parser.add_argument("--workers", type=int, default=4, help="Data loader workers")
    parser.add_argument("--patience", type=int, default=50, help="Early stopping patience")
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    data_path = Path(args.data)
    if not data_path.exists():
        raise FileNotFoundError(f"Dataset YAML not found: {data_path}")


def main() -> None:
    args = parse_args()
    validate_args(args)

    model = YOLO(args.model)
    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        project=args.project,
        name=args.name,
        device=args.device,
        workers=args.workers,
        patience=args.patience,
    )


if __name__ == "__main__":
    main()