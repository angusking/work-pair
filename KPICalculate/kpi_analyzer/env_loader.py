from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .errors import InputValidationError


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_llm_config(env_path: Path = Path(".env")) -> LLMConfig:
    load_env_file(env_path)
    missing = [name for name in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL") if not os.getenv(name)]
    if missing:
        raise InputValidationError("Missing required .env variables: " + ", ".join(missing))
    base_url = os.environ["LLM_BASE_URL"].rstrip("/")
    return LLMConfig(
        base_url=base_url,
        api_key=os.environ["LLM_API_KEY"],
        model=os.environ["LLM_MODEL"],
    )

