import argparse
import shutil
from pathlib import Path
from typing import Tuple


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Organize dataset into canonical YOLO format")
    parser.add_argument("--base", default=".", help="Project root directory")
    parser.add_argument("--keep-legacy", action="store_true", help="Do not remove legacy train/valid/test folders")
    parser.add_argument("--classes", default="Ambulance", help="Comma-separated class names")
    return parser.parse_args()


def ensure_folders(base: Path) -> None:
    for folder in ("images/train", "images/val", "labels/train", "labels/val"):
        (base / folder).mkdir(parents=True, exist_ok=True)


def copy_split(source: Path, images_dest: Path, labels_dest: Path) -> Tuple[int, int]:
    images = 0
    labels = 0

    if not source.exists():
        return images, labels

    for item in source.rglob("*"):
        if not item.is_file():
            continue

        suffix = item.suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            shutil.copy2(item, images_dest / item.name)
            images += 1
        elif suffix == ".txt":
            shutil.copy2(item, labels_dest / item.name)
            labels += 1

    return images, labels


def write_data_yaml(base: Path, classes: list[str]) -> None:
    names_block = "\n".join(f"  {idx}: {name}" for idx, name in enumerate(classes))
    content = (
        "path: .\n"
        "train: images/train\n"
        "val: images/val\n"
        f"nc: {len(classes)}\n"
        "names:\n"
        f"{names_block}\n"
    )
    (base / "data.yaml").write_text(content, encoding="utf-8")


def maybe_remove_legacy(base: Path) -> None:
    for folder in ("train", "valid", "test"):
        target = base / folder
        if target.exists() and target.is_dir():
            shutil.rmtree(target)


def main() -> None:
    args = parse_args()
    base = Path(args.base).resolve()
    classes = [name.strip() for name in args.classes.split(",") if name.strip()]

    if not classes:
        raise ValueError("At least one class name is required")

    ensure_folders(base)

    train_images, train_labels = copy_split(
        source=base / "train",
        images_dest=base / "images" / "train",
        labels_dest=base / "labels" / "train",
    )
    val_images, val_labels = copy_split(
        source=base / "valid",
        images_dest=base / "images" / "val",
        labels_dest=base / "labels" / "val",
    )

    write_data_yaml(base, classes)

    if not args.keep_legacy:
        maybe_remove_legacy(base)

    print("Dataset organization complete")
    print(f"train images: {train_images}, train labels: {train_labels}")
    print(f"val images: {val_images}, val labels: {val_labels}")
    print("Updated data.yaml with relative paths")


if __name__ == "__main__":
    main()