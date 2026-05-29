from __future__ import annotations

from datetime import datetime


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def make_run_id() -> str:
    return "run_" + datetime.now().strftime("%Y%m%d_%H%M%S")


def safe_filename_part(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value)

