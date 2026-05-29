from __future__ import annotations

from pathlib import Path
from threading import Lock

from .utils import now_iso


class RunLogger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def _write(self, level: str, message: str) -> None:
        line = f"[{now_iso()}] {level:<5} {message}"
        with self._lock:
            print(line)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    def info(self, message: str) -> None:
        self._write("INFO", message)

    def warn(self, message: str) -> None:
        self._write("WARN", message)

    def error(self, message: str) -> None:
        self._write("ERROR", message)

