## 1. Project Overview (High-Level)

- This is an edge AI + IoT traffic control prototype built around object detection with YOLO.
- Core goal: detect vehicle density and ambulance presence from live camera streams, then send lane-priority timing commands to a Raspberry Pi traffic-light controller.
- Application type: Computer Vision / ML inference system with socket-based device control (not a web app, not a REST API).
- Intended users:
1. Student/research team building a smart intersection demo.
2. Embedded/IoT operator running Raspberry Pi signal hardware.
3. Developer retraining models and tuning traffic logic.

Primary implementation is in traffic_density_yolo.py, with data prep helpers in organize_dataset.py and train.py.

---

## 2. Tech Stack Breakdown

- Python:
Used across all scripts for CV, sockets, automation.
- Ultralytics YOLO:
Loaded in traffic_density_yolo.py and model path set in traffic_density_yolo.py. Chosen for fast setup and strong real-time detection support.
- OpenCV:
Used for camera capture, frame resize, rendering overlays in traffic_density_yolo.py. Chosen for robust camera/video handling.
- Socket networking (TCP):
Used to send control messages to Pi in traffic_density_yolo.py and a separate client in basic.py. Chosen for simple low-latency LAN communication.
- Threading:
Video capture/inference runs in a background thread in traffic_density_yolo.py. Chosen to keep control loop active.
- Dataset and training artifacts:
YOLO dataset yaml in data.yaml, source dataset copy in data.yaml, and many train outputs in detect.

Outdated or unnecessary tech/patterns:
1. Hardcoded absolute Windows paths in data.yaml, organize_dataset.py, train.py, dum2.py reduce portability.
2. No dependency manifest (no requirements file / pyproject), making setup fragile.
3. train.py is not actual model training code despite name; it only validates folder structure.
4. Unicode-heavy console output is fine for demos but can break in some terminals/logging environments.

---

## 3. Folder & File Structure Explanation

Major folders:
1. Ambulance.v1i.yolov8:
Original Roboflow export (its own train/valid/test and yaml).
2. images and labels:
Reorganized YOLO layout used by root-level data.yaml.
3. train, valid, test:
Another dataset layout version; appears intermediate/raw.
4. detect:
YOLO experiment outputs (metrics, weights, predictions).
5. .venv and yolov8env:
Two Python env directories exist, which can cause confusion.

Entry points:
1. Runtime control app: traffic_density_yolo.py
2. Simple manual socket sender: basic.py
3. Dataset organizer: organize_dataset.py
4. Dataset inspector/debugger: dum2.py
5. Structure checker (misnamed as trainer): train.py

Read-first files:
1. traffic_density_yolo.py
2. data.yaml
3. organize_dataset.py
4. README.roboflow.txt
5. args.yaml

---

## 4. How to Run the Project (VERY IMPORTANT)

Prerequisites:
1. Windows with PowerShell.
2. Python 3.10 to 3.12 recommended.
3. Camera stream URLs reachable over LAN.
4. Raspberry Pi listener running on expected IP/port.
5. GPU optional (CPU works slower).

Step-by-step setup:
1. Open terminal at workspace root:
D:/Projects/Final Project Iot
2. Create venv if needed:
python -m venv .venv
3. If activation is blocked by PowerShell policy, run:
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process
4. Activate venv:
Activate.ps1
5. Install dependencies:
pip install ultralytics opencv-python
6. Verify imports:
python -c "import cv2; from ultralytics import YOLO; print('ok')"

Environment/config setup:
1. Update model path if needed in traffic_density_yolo.py.
2. Fix Raspberry Pi IP string in traffic_density_yolo.py because it currently includes extra characters/spaces.
3. Update camera URLs in traffic_density_yolo.py.
4. Ensure data.yaml path points to your current machine path, not old OneDrive path.

Database setup:
- None. This project does not use a DB.

Run commands:
1. Start the traffic AI controller:
python traffic_density_yolo.py
2. Optional manual socket sender test:
python basic.py
3. Optional dataset reorganization:
python organize_dataset.py
4. Optional structure check:
python train.py

Common errors and fixes:
1. PowerShell not digitally signed:
Use Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass.
2. Cannot open camera:
Check URL, phone camera app, LAN IP reachability, firewall.
3. Cannot connect to Pi:
Verify Pi server is listening on matching IP/port.
4. Model load fail:
Check model file exists (for example new.pt in root).
5. Data path not found during training:
Fix data.yaml absolute path to current workspace.

---

## 5. Execution Flow (End-to-End)

App startup flow:
1. Script starts in traffic_density_yolo.py.
2. YOLO model is loaded from new.pt in traffic_density_yolo.py.
3. Camera streams are initialized in traffic_density_yolo.py.
4. Background capture thread starts via traffic_density_yolo.py.

Frame/data flow:
1. Each frame is read from each camera.
2. analyze_frame runs inference and class parsing in traffic_density_yolo.py.
3. Vehicle count per lane is updated in traffic_density_yolo.py.
4. Ambulance confirmation requires continuous detection for 10 seconds in traffic_density_yolo.py.
5. Priority order is computed by count in traffic_density_yolo.py.
6. Command string like LANE1:20:5,... is sent over TCP in traffic_density_yolo.py.

API flow:
- No HTTP API exists. Communication is raw TCP sockets only.

ML model flow:
1. Input frame.
2. YOLO detection result.
3. Class-name-based rule mapping:
Ambulance flag and vehicle counting.
4. Control logic maps counts to fixed green/yellow presets.
5. Output is signal timing command string to Pi.

---

## 6. Key Features Breakdown

1. Multi-lane real-time detection
- What it does:
Processes camera streams and counts traffic objects.
- Files:
traffic_density_yolo.py, traffic_density_yolo.py, traffic_density_yolo.py
- Internals:
Reads frames, runs YOLO inference, parses class names, stores per-lane counts.

2. Ambulance priority override
- What it does:
Overrides normal cycle when ambulance is confirmed for 10 seconds.
- Files:
traffic_density_yolo.py, traffic_density_yolo.py
- Internals:
Starts a timer per lane, flips ambulance_active, prepends ambulance lane in output order.

3. Traffic density scheduling
- What it does:
Sorts lanes by detected vehicle counts.
- Files:
traffic_density_yolo.py
- Internals:
Sort descending by count; map rank to fixed green/yellow arrays.

4. Raspberry Pi command dispatch
- What it does:
Sends lane timing commands via TCP.
- Files:
traffic_density_yolo.py, basic.py
- Internals:
Creates client socket, connects, sends encoded text payload.

5. Dataset restructuring utility
- What it does:
Moves/copies files into YOLO images/labels train/val structure.
- Files:
organize_dataset.py
- Internals:
Scans source split folders, copies images and labels, writes data.yaml.

---

## 7. Code Quality Review (Be Honest)

Bad practices:
1. Hardcoded machine-specific paths all over project:
data.yaml, organize_dataset.py, train.py, dum2.py.
2. Misleading naming:
train.py does not train.
3. Inconsistent dataset configs:
Root data.yaml is single-class; data.yaml has 5 classes.
4. No config file or env vars for IP/ports/model path.

Security issues:
1. Plain unauthenticated socket traffic to actuator endpoint.
2. No message integrity, replay protection, or authorization.
3. No input validation on control messages.

Performance issues:
1. Sequential inference per camera in one thread may bottleneck with more streams.
2. Recreating socket connection on every send in traffic_density_yolo.py adds overhead.
3. Fixed sleep cycles can delay responsiveness to changing traffic.

Scalability problems:
1. Lane arrays initialized for 4 lanes but camera list currently has 2 entries in traffic_density_yolo.py.
2. Logic is tightly coupled to fixed-length duration arrays.
3. No modular separation between detection, decision, and communication layers.

Missing components:
1. No tests.
2. No dependency lock/manifest.
3. No logging framework.
4. No CI pipeline.
5. No deployment docs.

---

## 8. What is NOT Working / Missing

Likely broken/incomplete:
1. Raspberry Pi IP string appears malformed in traffic_density_yolo.py, likely causing connection failure.
2. Claimed “all 4 lanes” message mismatches actual camera list size in traffic_density_yolo.py vs traffic_density_yolo.py.
3. Training workflow is incomplete:
train.py only checks folders; there is no true training script command logic.
4. Dataset handling is fragmented:
Multiple parallel dataset layouts can cause accidental mis-training.
5. No robust failure handling:
Camera disconnect only logs warning; no reconnection/backoff strategy.

Placeholder or demo-grade implementations:
1. basic.py is a manual socket test tool, not production.
2. Hardcoded constants for timings and infrastructure endpoints.
3. No calibration strategy per camera/lane geometry.

---

## 9. How I Should Start Working on This Project

What to read first:
1. traffic_density_yolo.py
2. data.yaml
3. organize_dataset.py
4. args.yaml

What to run first:
1. Minimal sanity:
python -c "from ultralytics import YOLO; import cv2; print('ready')"
2. Single script smoke test:
python traffic_density_yolo.py
3. Dataset checks:
python train.py

Small beginner-friendly changes:
1. Move all hardcoded IP/port/path values into a config file.
2. Rename train.py to something like validate_dataset.py.
3. Fix malformed Pi IP in traffic_density_yolo.py.
4. Add one command-line flag for model path and camera URLs.

Beginner entry points:
1. Config management.
2. Logging improvements.
3. Better error messages and reconnection logic.

---

## 10. Improvement Roadmap

Immediate fixes (today):
1. Fix traffic_density_yolo.py Pi IP value.
2. Align lane count arrays with actual camera list length.
3. Replace absolute paths with relative paths and environment variables.
4. Add requirements.txt and setup instructions.

Medium improvements (this sprint):
1. Split code into modules:
detection, scheduling, communication.
2. Add retry/backoff for camera and socket failures.
3. Add unit tests for scheduling and message formatting.
4. Build a real training script with CLI arguments and experiment tracking.

Advanced production upgrades:
1. Secure communication channel to traffic controller.
2. Introduce queue/broker or reliable messaging protocol.
3. Add model serving abstraction and performance profiling.
4. Add observability:
structured logs, health checks, metrics dashboard.
5. Support dynamic traffic policy optimization (not fixed duration mapping).

---

## 11. Explain Like I'm Learning

Think of the system like a human traffic officer with a walkie-talkie:

1. Eyes:
YOLO is the eye that watches each lane and recognizes vehicles/ambulances.
2. Brain:
The scheduling logic decides who gets green first based on “how crowded” each lane is.
3. Emergency rule:
If it sees an ambulance steadily for 10 seconds, the brain pauses normal rules and gives that lane immediate priority.
4. Voice:
Socket code is the walkie-talkie that sends instructions to the Raspberry Pi.

Simple example:
- Lane counts become [15, 4, 9, 2].
- Brain sorts by density: lane 1, lane 3, lane 2, lane 4.
- It sends:
LANE1:20:5,LANE3:15:5,LANE2:10:5,LANE4:10:5
- If ambulance appears in lane 2 and stays:
LANE2 gets forced to top until ambulance clears.

Confidence note:
You can safely start modifying this project once you stabilize configuration and separate concerns. Right now it is a good prototype, but not yet robust enough for production traffic control without the fixes above.

Natural next steps:
1. I can generate a clean requirements.txt and a runnable training script that actually calls YOLO training.
2. I can refactor traffic_density_yolo.py into modular files while preserving behavior.
3. I can add a config file and remove all hardcoded IP/path values in one pass.