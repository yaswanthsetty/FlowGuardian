# Smart Traffic Control System (Hybrid AI + IoT)

## Overview
This project controls a traffic junction using multiple camera feeds, YOLO models, a hybrid scheduler, and Raspberry Pi socket-based signal execution.

Core objective:
- NORMAL mode by default with fixed timings.
- OVERRIDE mode only when ambulance is confirmed or lane density is high.
- Accident model is monitoring and alert only (no direct timing override).

## Model Usage
- new.pt
  Role: vehicle counting for density estimation.
  Used by: detection/yolo_detector.py

- models/bestamb.pt
  Role: ambulance detection only.
  Used by: detection/ambulance_detector.py

- models/accident_model.pt
  Role: accident monitoring and alert only.
  Used by: logic/accident_ml.py

## Hybrid Control Modes
- NORMAL
  - Lane order: 1..N
  - Green/yellow durations from DEFAULT_GREEN_DURATIONS and DEFAULT_YELLOW_DURATIONS
  - Reason: default

- OVERRIDE
  Triggered when:
  - Ambulance is confirmed after temporal validation (5-10 seconds), or
  - max(vehicle_count) > DENSITY_OVERRIDE_THRESHOLD

  Behavior:
  - Ambulance lane gets highest priority when active.
  - Otherwise lanes are sorted by density.
  - Green time is distributed proportionally using TOTAL_OVERRIDE_CYCLE_TIME.
  - Reason: ambulance or density

## Runtime Workflow
Camera -> Vehicle model -> Ambulance model -> Accident model -> Scheduler -> Socket -> Raspberry Pi -> Traffic lights

Detailed flow:
1. main.py reads config from .env via config.py.
2. For each lane camera:
   - Vehicle model updates lane counts.
   - Dedicated ambulance model detects ambulance candidates.
   - Scheduler applies per-lane ambulance temporal validation.
   - Accident model runs periodically for monitoring overlays/alerts only.
3. Scheduler returns mode + lane order + timings.
4. Controller sends timing string to Raspberry Pi over TCP.
5. Optional cloud payload is sent on configured interval.

## Raspberry Pi Communication
Current control message format from runtime:
- LANE1:20:5,LANE2:20:5,LANE3:20:5,LANE4:20:5

Each segment means:
- LANE<id>:<green_seconds>:<yellow_seconds>

Compatibility:
- Raspberry Pi parser in raspberry_pi_server.py also accepts LANE1:20 format (yellow defaults to 5).

## Multi-Lane Support
The system supports 3-lane, 4-lane, or N-lane setups.

Requirements:
- Set CAMERA_URLS with exactly one URL per lane.
- Provide default timing lists (they are auto-expanded by scheduler if shorter).
- For Raspberry Pi GPIO control, map lane pins in raspberry_pi_server.py for the lanes you physically use.

## Project Structure
- main.py
- config.py
- detection/
  - yolo_detector.py
  - ambulance_detector.py
- logic/
  - traffic_scheduler.py
  - accident_ml.py
- communication/
  - socket_client.py
  - cloud_sync.py
- raspberry_pi_server.py
- .env.example
- requirements.txt

## Setup
### 1. Install dependencies
```powershell
pip install -r requirements.txt
```

### 2. Prepare environment file
```powershell
copy .env.example .env
```

### 3. Configure .env
Important keys:
- MODEL_PATH=new.pt
- AMBULANCE_MODEL_PATH=models/bestamb.pt
- ACCIDENT_MODEL_PATH=models/accident_model.pt
- CAMERA_URLS=http://cam1/video,http://cam2/video,http://cam3/video
- PI_HOST=<raspberry_pi_ip>
- PI_PORT=7000
- DEFAULT_GREEN_DURATIONS=20,20,20,20
- DEFAULT_YELLOW_DURATIONS=5,5,5,5
- DENSITY_OVERRIDE_THRESHOLD=15
- TOTAL_OVERRIDE_CYCLE_TIME=80
- AMBULANCE_CONFIRM_SECONDS=8
- CLOUD_SYNC_ENABLED=0 or 1

### 4. Place model files
- new.pt at project root (or set MODEL_PATH)
- bestamb.pt under models/ (or set AMBULANCE_MODEL_PATH)
- accident_model.pt under models/

### 5. Run controller
```powershell
python main.py
```

### 6. Run Raspberry Pi server
On Raspberry Pi:
```bash
python3 raspberry_pi_server.py
```

## Cloud Sync Payload (optional)
If CLOUD_SYNC_ENABLED=1, payload includes:
- mode
- reason
- junction_id
- lane_order
- lanes[] with green/yellow/vehicle_count
- ambulance_lane
- accident_alert {active, lane, confidence}
- timestamp

## Troubleshooting
- Camera not opening:
  - Check CAMERA_URLS reachability and stream availability.
  - Verify FRAME_WIDTH/FRAME_HEIGHT are supported by the stream.

- Socket send failures:
  - Ensure Raspberry Pi server is running on PI_HOST:PI_PORT.
  - Check firewall and local network routing.

- Model load errors:
  - Verify .pt files exist at configured paths.
  - Ensure ultralytics is installed in the active environment.

- No ambulance override:
  - Confirm bestamb.pt has an ambulance class label.
  - Increase AMBULANCE_CONFIRM_SECONDS only if needed.
  - Lower AMBULANCE_CONF_THRESHOLD if detections are too strict.

- GPIO issues on Raspberry Pi:
  - Update lane pin mapping in raspberry_pi_server.py.
  - Run with proper permissions when using RPi.GPIO.

## Notes
- Accident detection is intentionally alert-only and does not alter signal timings.
- Socket retry logic is handled by communication/socket_client.py so temporary network issues do not crash runtime.
