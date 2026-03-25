from ultralytics import YOLO

model = YOLO("models/accident_model.pt")

results = model("image.png", show=True)

print(results)