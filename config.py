import os
from dataclasses import dataclass
from pathlib import Path
from typing import List


def _split_csv(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[7:].strip()

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key:
            continue

        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]

        os.environ.setdefault(key, value)


@dataclass
class Settings:
    model_path: str
    device: str
    primary_conf_threshold: float
    frame_skip: int
    accident_model_path: str
    accident_conf_threshold: float
    accident_frame_skip: int
    camera_urls: List[str]
    pi_host: str
    pi_port: int
    enable_pi: bool
    initial_wait_seconds: int
    frame_width: int
    frame_height: int
    ambulance_confirm_seconds: int
    ambulance_detection_threshold: int
    ambulance_miss_threshold: int
    camera_retry_seconds: int
    stale_decay_factor: float
    socket_retry_seconds: int
    connect_timeout_seconds: float
    send_timeout_seconds: float
    default_green_durations: List[int]
    default_yellow_durations: List[int]
    density_override_threshold: int
    total_override_cycle_time: int
    fairness_wait_weight: float
    max_consecutive_priority_cycles: int
    override_min_green_seconds: int
    override_max_green_seconds: int
    emergency_green_seconds: int
    control_mode: str
    control_interval_seconds: int
    cycle_sleep_tick_seconds: float
    normal_decision_lock_seconds: float
    min_green_time: int
    max_green_time: int
    cloud_sync_enabled: bool
    cloud_sync_interval_seconds: int
    cloud_queue_size: int
    cloud_request_timeout_seconds: float
    cloud_max_retries: int
    cloud_retry_backoff_seconds: float
    cloud_api_url: str
    junction_id: str
    full_signal_logging: bool
    show_windows: bool


DEFAULT_CAMERA = "http://127.0.0.1:8080/video"
ACCIDENT_MODEL_PATH = "models/accident_model.pt"
ACCIDENT_CONF_THRESHOLD = 0.6
ACCIDENT_FRAME_SKIP = 5
DEFAULT_GREEN_DURATIONS = "20,20,20,20"
DEFAULT_YELLOW_DURATIONS = "5,5,5,5"


def load_settings() -> Settings:
    project_root = Path(__file__).resolve().parent
    _load_dotenv(project_root / ".env")
    model_path = os.getenv("MODEL_PATH", str(project_root / "models" / "new.pt"))

    camera_urls_raw = os.getenv("CAMERA_URLS", DEFAULT_CAMERA)
    camera_urls = _split_csv(camera_urls_raw)

    if not camera_urls:
        raise ValueError("CAMERA_URLS is empty. Provide at least one URL.")

    green_raw = os.getenv("DEFAULT_GREEN_DURATIONS", os.getenv("GREEN_DURATIONS", DEFAULT_GREEN_DURATIONS))
    yellow_raw = os.getenv("DEFAULT_YELLOW_DURATIONS", os.getenv("YELLOW_DURATIONS", DEFAULT_YELLOW_DURATIONS))

    default_green_durations = [int(x) for x in _split_csv(green_raw)]
    default_yellow_durations = [int(x) for x in _split_csv(yellow_raw)]

    return Settings(
        model_path=model_path,
        device=os.getenv("DEVICE", "auto"),
        primary_conf_threshold=float(os.getenv("PRIMARY_CONF_THRESHOLD", "0.35")),
        frame_skip=max(1, int(os.getenv("FRAME_SKIP", "3"))),
        accident_model_path=os.getenv("ACCIDENT_MODEL_PATH", str(project_root / ACCIDENT_MODEL_PATH)),
        accident_conf_threshold=float(os.getenv("ACCIDENT_CONF_THRESHOLD", str(ACCIDENT_CONF_THRESHOLD))),
        accident_frame_skip=max(1, int(os.getenv("ACCIDENT_FRAME_SKIP", str(ACCIDENT_FRAME_SKIP)))),
        camera_urls=camera_urls,
        pi_host=os.getenv("PI_HOST", "10.10.8.138"),
        pi_port=int(os.getenv("PI_PORT", "7000")),
        enable_pi=os.getenv("ENABLE_PI", "0") == "1",
        initial_wait_seconds=int(os.getenv("INITIAL_WAIT_SECONDS", "5")),
        frame_width=int(os.getenv("FRAME_WIDTH", "640")),
        frame_height=int(os.getenv("FRAME_HEIGHT", "480")),
        ambulance_confirm_seconds=int(os.getenv("AMBULANCE_CONFIRM_SECONDS", "10")),
        ambulance_detection_threshold=max(1, int(os.getenv("AMBULANCE_DETECTION_THRESHOLD", "2"))),
        ambulance_miss_threshold=max(1, int(os.getenv("AMBULANCE_MISS_THRESHOLD", "3"))),
        camera_retry_seconds=int(os.getenv("CAMERA_RETRY_SECONDS", "3")),
        stale_decay_factor=min(1.0, max(0.0, float(os.getenv("STALE_DECAY_FACTOR", "0.5")))),
        socket_retry_seconds=int(os.getenv("SOCKET_RETRY_SECONDS", "3")),
        connect_timeout_seconds=float(os.getenv("SOCKET_CONNECT_TIMEOUT", "3")),
        send_timeout_seconds=float(os.getenv("SOCKET_SEND_TIMEOUT", "2")),
        default_green_durations=default_green_durations,
        default_yellow_durations=default_yellow_durations,
        density_override_threshold=int(os.getenv("DENSITY_OVERRIDE_THRESHOLD", "15")),
        total_override_cycle_time=int(os.getenv("TOTAL_OVERRIDE_CYCLE_TIME", "80")),
        fairness_wait_weight=max(0.0, float(os.getenv("FAIRNESS_WAIT_WEIGHT", "2.0"))),
        max_consecutive_priority_cycles=max(1, int(os.getenv("MAX_CONSECUTIVE_PRIORITY_CYCLES", "2"))),
        override_min_green_seconds=max(1, int(os.getenv("OVERRIDE_MIN_GREEN_SECONDS", "8"))),
        override_max_green_seconds=max(1, int(os.getenv("OVERRIDE_MAX_GREEN_SECONDS", "40"))),
        emergency_green_seconds=max(1, int(os.getenv("EMERGENCY_GREEN_SECONDS", "15"))),
        control_mode=os.getenv("CONTROL_MODE", "cycle").strip().lower(),
        control_interval_seconds=max(1, int(os.getenv("CONTROL_INTERVAL_SECONDS", "5"))),
        cycle_sleep_tick_seconds=max(0.05, float(os.getenv("CYCLE_SLEEP_TICK_SECONDS", "0.2"))),
        normal_decision_lock_seconds=max(0.0, float(os.getenv("NORMAL_DECISION_LOCK_SECONDS", "10"))),
        min_green_time=max(1, int(os.getenv("MIN_GREEN_TIME", "5"))),
        max_green_time=max(1, int(os.getenv("MAX_GREEN_TIME", "10"))),
        cloud_sync_enabled=os.getenv("CLOUD_SYNC_ENABLED", "0") == "1",
        cloud_sync_interval_seconds=int(os.getenv("CLOUD_SYNC_INTERVAL_SECONDS", "10")),
        cloud_queue_size=max(1, int(os.getenv("CLOUD_QUEUE_SIZE", "50"))),
        cloud_request_timeout_seconds=max(1.0, float(os.getenv("CLOUD_REQUEST_TIMEOUT_SECONDS", "5"))),
        cloud_max_retries=max(0, int(os.getenv("CLOUD_MAX_RETRIES", "2"))),
        cloud_retry_backoff_seconds=max(
            0.1,
            float(os.getenv("CLOUD_BACKOFF_SECONDS", os.getenv("CLOUD_RETRY_BACKOFF_SECONDS", "0.5"))),
        ),
        cloud_api_url=os.getenv("CLOUD_API_URL", ""),
        junction_id=os.getenv("JUNCTION_ID", "J1"),
        full_signal_logging=os.getenv("FULL_SIGNAL_LOGGING", "0") == "1",
        show_windows=os.getenv("SHOW_WINDOWS", "1") == "1",
    )
