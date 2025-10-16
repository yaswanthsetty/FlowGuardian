import cv2
from ultralytics import YOLO
import time
import socket

# ------------------- YOLO Model -------------------
model = YOLO("yolov8n.pt")  # Pre-trained YOLOv8 model

# ------------------- Vehicle counting function -------------------
def count_vehicles(frame):
    """
    Detects vehicles in the frame using YOLOv8 and returns:
    - vehicle_count: number of detected vehicles
    - annotated_frame: frame with bounding boxes drawn
    """
    results = model(frame)  # Run inference
    annotated_frame = results[0].plot()  # Draw YOLO boxes automatically

    vehicle_count = 0
    for box in results[0].boxes:
        cls_id = int(box.cls[0])
        # COCO classes for vehicles
        if cls_id in [2, 3, 5, 7]:  # car, motorcycle, bus, truck
            vehicle_count += 1

    return vehicle_count, annotated_frame


# ------------------- TCP Client Setup -------------------
PI_IP = "172.15.6.17"  # <-- Replace with your Raspberry Pi IP
PORT = 5000            # Must match server port

def send_to_pi(lane):
    """Send lane info to Raspberry Pi"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((PI_IP, PORT))
            s.sendall(lane.encode())
            print(f"✅ Sent to Raspberry Pi: {lane}")
    except Exception as e:
        print(f"⚠️ Failed to send data to Raspberry Pi: {e}")


# ------------------- Mobile Camera Setup -------------------
camera_url = "http://192.168.137.116:8080/video"  # Mobile IP Webcam URL
cap = cv2.VideoCapture(camera_url)

if not cap.isOpened():
    print("❌ Cannot open mobile camera stream. Check URL or Wi-Fi connection.")
    exit()

lane_counts = []

try:
    for i in range(2):
        print(f"\n--- Show traffic for Lane {i+1} using your mobile camera ---")
        input("Press Enter when ready...")  # wait for user to start showing video

        start_time = time.time()
        vehicle_count = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                print("⚠️ Lost camera connection. Reconnecting...")
                cap = cv2.VideoCapture(camera_url)
                time.sleep(2)
                continue

            frame = cv2.resize(frame, (640, 480))

            # Count and draw vehicles
            vehicle_count, annotated_frame = count_vehicles(frame)

            # Display vehicle count
            cv2.putText(annotated_frame, f"Vehicles: {vehicle_count}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)
            cv2.imshow("Mobile Camera Feed", annotated_frame)

            # Run each lane capture for 10 seconds or until user presses 'q'
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            if time.time() - start_time > 10:
                break

        lane_counts.append(vehicle_count)
        print(f"✅ Lane {i+1} finished. Detected {vehicle_count} vehicles.")

finally:
    cap.release()
    cv2.destroyAllWindows()


# ------------------- Compare lanes and send to Raspberry Pi -------------------
if len(lane_counts) < 2:
    print("⚠️ Not enough lane data collected.")
    exit()

lane1_count, lane2_count = lane_counts
print("\n=== 🚦 Traffic Density Result ===")

tolerance = 2  # difference threshold

if abs(lane1_count - lane2_count) <= tolerance:
    # Counts are close, prefer the higher one
    if lane1_count >= lane2_count:
        print(f"Lanes are close, preferring Lane 1 ({lane1_count} vs {lane2_count})")
        send_to_pi("LANE1")
    else:
        print(f"Lanes are close, preferring Lane 2 ({lane2_count} vs {lane1_count})")
        send_to_pi("LANE2")
elif lane1_count > lane2_count:
    print(f"Lane 1 has more traffic ({lane1_count} vs {lane2_count})")
    send_to_pi("LANE1")
else:
    print(f"Lane 2 has more traffic ({lane2_count} vs {lane1_count})")
    send_to_pi("LANE2")
