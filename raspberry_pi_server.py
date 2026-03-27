import socket
import time
from typing import List, Tuple

try:
    import RPi.GPIO as GPIO  # type: ignore
except Exception:
    GPIO = None


HOST = "0.0.0.0"
PORT = 7000
BACKLOG = 1
BUFFER_SIZE = 4096
ALL_RED_SECONDS = 1

# Update these pins for your board wiring (BCM numbering)
LANE_PINS = {
    1: {"red": 17, "yellow": 27, "green": 22},
    2: {"red": 5, "yellow": 6, "green": 13},
    3: {"red": 19, "yellow": 26, "green": 21},
    4: {"red": 20, "yellow": 16, "green": 12},
}


def parse_signal_plan(message: str) -> List[Tuple[int, int, int]]:
    # Accept formats:
    # LANE1:20:5,LANE2:10:5
    # LANE1:20,LANE2:10
    plan: List[Tuple[int, int, int]] = []
    if not message.strip():
        return plan

    chunks = [chunk.strip() for chunk in message.split(",") if chunk.strip()]
    for chunk in chunks:
        if not chunk.upper().startswith("LANE"):
            raise ValueError(f"Invalid chunk '{chunk}'")

        body = chunk[4:]
        parts = [part.strip() for part in body.split(":") if part.strip()]
        if len(parts) < 2:
            raise ValueError(f"Invalid lane format '{chunk}'")

        lane = int(parts[0])
        green = int(parts[1])
        yellow = int(parts[2]) if len(parts) >= 3 else 5

        if lane <= 0 or green < 0 or yellow < 0:
            raise ValueError(f"Invalid values in '{chunk}'")

        plan.append((lane, green, yellow))

    return plan


def setup_gpio() -> None:
    if GPIO is None:
        print("GPIO library not available; running in simulation mode")
        return

    GPIO.setmode(GPIO.BCM)
    for lane_cfg in LANE_PINS.values():
        for pin in lane_cfg.values():
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)


def set_all_red() -> None:
    if GPIO is None:
        print("[SIM] all-red")
        return

    for lane_cfg in LANE_PINS.values():
        GPIO.output(lane_cfg["red"], GPIO.HIGH)
        GPIO.output(lane_cfg["yellow"], GPIO.LOW)
        GPIO.output(lane_cfg["green"], GPIO.LOW)


def activate_lane(lane: int, green_seconds: int, yellow_seconds: int) -> None:
    if lane not in LANE_PINS:
        print(f"[WARN] Lane {lane} has no pin mapping; skipping")
        return

    if GPIO is None:
        print(f"[SIM] Lane {lane} GREEN {green_seconds}s then YELLOW {yellow_seconds}s")
        time.sleep(green_seconds + yellow_seconds)
        return

    set_all_red()
    time.sleep(ALL_RED_SECONDS)

    lane_cfg = LANE_PINS[lane]

    GPIO.output(lane_cfg["red"], GPIO.LOW)
    GPIO.output(lane_cfg["green"], GPIO.HIGH)
    time.sleep(green_seconds)

    GPIO.output(lane_cfg["green"], GPIO.LOW)
    GPIO.output(lane_cfg["yellow"], GPIO.HIGH)
    time.sleep(yellow_seconds)

    GPIO.output(lane_cfg["yellow"], GPIO.LOW)
    GPIO.output(lane_cfg["red"], GPIO.HIGH)


def run_plan(plan: List[Tuple[int, int, int]]) -> None:
    for lane, green, yellow in plan:
        activate_lane(lane, green, yellow)


def run_server() -> None:
    setup_gpio()
    set_all_red()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(BACKLOG)

    print(f"Raspberry Pi traffic server listening on {HOST}:{PORT}")

    try:
        while True:
            conn, addr = server.accept()
            print(f"Connected: {addr}")
            with conn:
                while True:
                    data = conn.recv(BUFFER_SIZE)
                    if not data:
                        break

                    message = data.decode("utf-8", errors="ignore").strip()
                    if not message:
                        continue

                    try:
                        plan = parse_signal_plan(message)
                        if not plan:
                            print("[WARN] Empty plan received")
                            continue

                        print(f"[PLAN] {plan}")
                        run_plan(plan)
                    except Exception as exc:
                        print(f"[ERROR] Invalid message '{message}': {exc}")
                        set_all_red()
    finally:
        set_all_red()
        if GPIO is not None:
            GPIO.cleanup()
        server.close()


if __name__ == "__main__":
    run_server()
