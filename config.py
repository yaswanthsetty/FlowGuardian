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
    ambulance_model_path: str
    ambulance_conf_threshold: float
    ambulance_frame_skip: int
    accident_model_path: str
    accident_conf_threshold: float
    accident_frame_skip: int
    camera_urls: List[str]
    pi_host: str
    pi_port: int
    initial_wait_seconds: int
    frame_width: int
    frame_height: int
    ambulance_confirm_seconds: int
    camera_retry_seconds: int
    socket_retry_seconds: int
    connect_timeout_seconds: float
    send_timeout_seconds: float
    default_green_durations: List[int]
    default_yellow_durations: List[int]
    density_override_threshold: int
    total_override_cycle_time: int
    cloud_sync_enabled: bool
    cloud_sync_interval_seconds: int
    cloud_api_url: str
    junction_id: str
    show_windows: bool


DEFAULT_CAMERA = "http://127.0.0.1:8080/video"
AMBULANCE_MODEL_PATH = "models/bestamb.pt"
AMBULANCE_CONF_THRESHOLD = 0.5
AMBULANCE_FRAME_SKIP = 2
ACCIDENT_MODEL_PATH = "models/accident_model.pt"
ACCIDENT_CONF_THRESHOLD = 0.6
ACCIDENT_FRAME_SKIP = 5
DEFAULT_GREEN_DURATIONS = "20,20,20,20"
DEFAULT_YELLOW_DURATIONS = "5,5,5,5"


def load_settings() -> Settings:
    project_root = Path(__file__).resolve().parent
    _load_dotenv(project_root / ".env")
    model_path = os.getenv("MODEL_PATH", str(project_root / "new.pt"))

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
        ambulance_model_path=os.getenv("AMBULANCE_MODEL_PATH", str(project_root / AMBULANCE_MODEL_PATH)),
        ambulance_conf_threshold=float(os.getenv("AMBULANCE_CONF_THRESHOLD", str(AMBULANCE_CONF_THRESHOLD))),
        ambulance_frame_skip=max(1, int(os.getenv("AMBULANCE_FRAME_SKIP", str(AMBULANCE_FRAME_SKIP)))),
        accident_model_path=os.getenv("ACCIDENT_MODEL_PATH", str(project_root / ACCIDENT_MODEL_PATH)),
        accident_conf_threshold=float(os.getenv("ACCIDENT_CONF_THRESHOLD", str(ACCIDENT_CONF_THRESHOLD))),
        accident_frame_skip=max(1, int(os.getenv("ACCIDENT_FRAME_SKIP", str(ACCIDENT_FRAME_SKIP)))),
        camera_urls=camera_urls,
        pi_host=os.getenv("PI_HOST", "10.10.8.138"),
        pi_port=int(os.getenv("PI_PORT", "7000")),
        initial_wait_seconds=int(os.getenv("INITIAL_WAIT_SECONDS", "5")),
        frame_width=int(os.getenv("FRAME_WIDTH", "640")),
        frame_height=int(os.getenv("FRAME_HEIGHT", "480")),
        ambulance_confirm_seconds=int(os.getenv("AMBULANCE_CONFIRM_SECONDS", "10")),
        camera_retry_seconds=int(os.getenv("CAMERA_RETRY_SECONDS", "3")),
        socket_retry_seconds=int(os.getenv("SOCKET_RETRY_SECONDS", "3")),
        connect_timeout_seconds=float(os.getenv("SOCKET_CONNECT_TIMEOUT", "3")),
        send_timeout_seconds=float(os.getenv("SOCKET_SEND_TIMEOUT", "2")),
        default_green_durations=default_green_durations,
        default_yellow_durations=default_yellow_durations,
        density_override_threshold=int(os.getenv("DENSITY_OVERRIDE_THRESHOLD", "15")),
        total_override_cycle_time=int(os.getenv("TOTAL_OVERRIDE_CYCLE_TIME", "80")),
        cloud_sync_enabled=os.getenv("CLOUD_SYNC_ENABLED", "0") == "1",
        cloud_sync_interval_seconds=int(os.getenv("CLOUD_SYNC_INTERVAL_SECONDS", "10")),
        cloud_api_url=os.getenv("CLOUD_API_URL", ""),
        junction_id=os.getenv("JUNCTION_ID", "J1"),
        show_windows=os.getenv("SHOW_WINDOWS", "1") == "1",
    )
