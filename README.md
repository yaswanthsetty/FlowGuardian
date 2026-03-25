# Smart Traffic Control System (Edge AI + IoT)

## Project Description
This project is a real-time smart traffic control system that combines computer vision and IoT control.

It uses:
- A YOLO model for vehicle and ambulance detection.
- A second YOLO model for accident detection.
- Live IP webcam streams as camera inputs.
- Lane scheduling logic with priority handling.
- TCP socket communication to send lane timing commands to a Raspberry Pi traffic controller.

Current lane priority order is:
1. Accident
2. Ambulance
3. Traffic density

The system is built as a modular Python application for easier maintenance and feature expansion.

## Key Features
- Real-time multi-lane camera ingestion using OpenCV.
- Vehicle counting per lane using YOLO detections.
- Ambulance detection with confirmation timing logic.
- Accident detection using a dedicated second YOLO model.
- Lane mapping from accident bounding boxes.
- Temporal accident confirmation to reduce false positives.
- Accident debounce lock for stable behavior during demos.
- Priority-aware scheduler for signal planning.
- Persistent TCP socket client with retry support.
- Structured logging for runtime visibility.

## System Architecture
The runtime is organized into clear modules:

- main.py
  Orchestrates camera capture, ML inference loops, state updates, overlays, scheduler calls, and socket dispatch.

- config.py
  Loads environment-driven runtime settings into a Settings object.

- detection/yolo_detector.py
  Runs primary YOLO inference for vehicle counting and ambulance detection.

- logic/accident_ml.py
  Runs accident model inference and returns normalized accident outputs.

- logic/traffic_scheduler.py
  Computes lane order and timings using Accident > Ambulance > Density priority.

- communication/socket_client.py
  Manages persistent TCP communication and send retries to Raspberry Pi.

- utils/logger.py
  Provides structured logger setup.

## Folder Structure
High-level structure (focused on core runtime and pipeline files):

- main.py
- config.py
- requirements.txt
- data.yaml
- train.py
- organize_dataset.py
- detection/
  - __init__.py
  - yolo_detector.py
- logic/
  - __init__.py
  - traffic_scheduler.py
  - accident_ml.py
- communication/
  - __init__.py
  - socket_client.py
- utils/
  - __init__.py
  - logger.py
- models/
  - accident_model.pt
- best.pt

Repository also contains dataset folders, training artifacts, and older experimental files.

## Tech Stack
- Python
- Ultralytics YOLO
- OpenCV
- Socket programming (TCP)
- Threading (Python stdlib)

## Model Details
Primary model:
- File: best.pt
- Used by: detection/yolo_detector.py
- Role: vehicle and ambulance detection

Accident model:
- File: models/accident_model.pt
- Used by: logic/accident_ml.py
- Role: accident detection

## IoT Integration (Raspberry Pi)
The application sends traffic signal plans over TCP to a Raspberry Pi endpoint.

Communication behavior:
- Persistent socket connection.
- Reconnect and resend on failure.
- Retry loop before reporting send failure.

Typical message format sent by scheduler:
- LANE1:20:5,LANE2:15:5,LANE3:10:5

Accident and ambulance event messages are also sent when detected and confirmed.

## How It Works
1. Start app and load runtime settings.
2. Open camera streams.
3. For each frame:
   - Run vehicle and ambulance detection.
   - Update lane counts and ambulance state.
   - Run accident model every configured N frames.
   - Map accident boxes to lane IDs.
   - Apply temporal confirmation and lock logic.
4. Build lane signal plan via scheduler.
5. Send signal plan to Raspberry Pi.
6. Show live annotated visualization windows.

## System Workflow (End-to-End)
Camera stream
-> frame capture
-> primary YOLO detection (vehicles + ambulance)
-> accident YOLO detection (periodic)
-> accident box to lane mapping
-> temporal validation and debounce lock
-> scheduler computes lane priority and timings
-> socket client sends commands to Raspberry Pi
-> Raspberry Pi drives traffic light sequence

## Quick Start Guide
1. Install dependencies.
2. Copy .env.example to .env and update values.
3. Configure IP webcam URLs, model paths, and Raspberry Pi endpoint in .env.
4. Run main.py.
5. Observe terminal logs and OpenCV windows.

Expected output:
- Live lane windows with vehicle counts.
- Ambulance and accident status overlays.
- Signal plan logs.
- Command sends to Raspberry Pi.

## Setup Instructions
### Prerequisites
- Python 3.10 or newer
- IP webcams reachable from the machine
- Raspberry Pi server listening for TCP commands
- YOLO model files present at configured paths

### Installation
1. Create or activate virtual environment.
2. Install dependencies:
   pip install -r requirements.txt
3. Create environment file:
  copy .env.example .env

### Data Configuration
- data.yaml defines the YOLO training dataset layout.
- Current classes in data.yaml are set to a single class (Ambulance).

## Running the Project
Run runtime:
- python main.py

Legacy entry (still available):
- python traffic_density_yolo.py

Run training pipeline:
- python train.py --model yolov8n.pt --data data.yaml --epochs 50

Organize dataset into canonical format:
- python organize_dataset.py --base . --keep-legacy

## Configuration (Environment Variables)
The runtime reads these values in config.py:

Primary detection:
- MODEL_PATH

Accident detection:
- ACCIDENT_MODEL_PATH
- ACCIDENT_CONF_THRESHOLD
- ACCIDENT_FRAME_SKIP

Cameras:
- CAMERA_URLS (comma-separated)
- FRAME_WIDTH
- FRAME_HEIGHT
- CAMERA_RETRY_SECONDS

Scheduler and timing:
- GREEN_DURATIONS (comma-separated)
- YELLOW_DURATIONS (comma-separated)
- AMBULANCE_CONFIRM_SECONDS
- INITIAL_WAIT_SECONDS

Raspberry Pi communication:
- PI_HOST
- PI_PORT
- SOCKET_CONNECT_TIMEOUT
- SOCKET_SEND_TIMEOUT
- SOCKET_RETRY_SECONDS

Visualization:
- SHOW_WINDOWS (1 or 0)

## Demo Explanation
During a demo, users will see:
- Live video feed per lane.
- Lane divider overlays.
- Vehicle count overlay text.
- Ambulance status overlay when detected.
- Accident bounding boxes and accident status overlays.
- Stable accident behavior due to temporal confirmation and lock duration.
- Continuous signal plan logs and socket send attempts.

## Requirements Check
The current requirements.txt aligns with imported external packages in core runtime and training files:
- ultralytics
- opencv-python

Other imports are from Python standard library.

## Future Improvements
- Add authenticated message protocol for Raspberry Pi communication.
- Add unit and integration tests for scheduler and accident state logic.
- Add health checks and telemetry export.
- Add camera stream watchdog metrics and reconnection dashboards.
- Add model confidence calibration utilities.
- Add optional ONNX export/inference path for edge optimization.

## Contributors
- Your Name Here
- Team Name Here
