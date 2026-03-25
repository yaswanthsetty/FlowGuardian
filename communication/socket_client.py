import socket
import threading
import time
from typing import Optional


class PersistentSocketClient:
    def __init__(
        self,
        host: str,
        port: int,
        connect_timeout: float = 3.0,
        send_timeout: float = 2.0,
        retry_seconds: int = 3,
        logger=None,
    ):
        self.host = host
        self.port = port
        self.connect_timeout = connect_timeout
        self.send_timeout = send_timeout
        self.retry_seconds = retry_seconds
        self.logger = logger

        self._socket: Optional[socket.socket] = None
        self._lock = threading.Lock()

    def _log(self, level: str, message: str) -> None:
        if self.logger is None:
            return
        getattr(self.logger, level)(message)

    def _connect_locked(self) -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.connect_timeout)
            sock.connect((self.host, self.port))
            sock.settimeout(self.send_timeout)
            self._socket = sock
            self._log("info", f"Socket connected to {self.host}:{self.port}")
            return True
        except OSError as exc:
            self._socket = None
            self._log("warning", f"Socket connect failed: {exc}")
            return False

    def ensure_connected(self) -> bool:
        with self._lock:
            if self._socket is not None:
                return True
            return self._connect_locked()

    def send(self, message: str) -> bool:
        payload = message.encode("utf-8")

        with self._lock:
            if self._socket is None and not self._connect_locked():
                return False

            try:
                self._socket.sendall(payload)
                return True
            except OSError as exc:
                self._log("warning", f"Socket send failed, reconnecting: {exc}")
                self._close_locked()

            if not self._connect_locked():
                return False

            try:
                self._socket.sendall(payload)
                return True
            except OSError as exc:
                self._log("error", f"Socket resend failed: {exc}")
                self._close_locked()
                return False

    def send_with_retry(self, message: str, attempts: int = 3) -> bool:
        for attempt in range(1, attempts + 1):
            if self.send(message):
                return True
            if attempt < attempts:
                self._log("warning", f"Retrying socket send ({attempt}/{attempts})")
                time.sleep(self.retry_seconds)
        return False

    def _close_locked(self) -> None:
        if self._socket is None:
            return
        try:
            self._socket.close()
        finally:
            self._socket = None

    def close(self) -> None:
        with self._lock:
            self._close_locked()
