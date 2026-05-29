from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from .constants import TEMPERATURE, TIMEOUT_SECONDS
from .env_loader import LLMConfig
from .errors import LLMError


@dataclass
class LLMCallResult:
    raw_response: str
    elapsed_seconds: float


class LLMClient:
    def __init__(self, config: LLMConfig):
        self.config = config

    async def request_once(self, prompt: str) -> LLMCallResult:
        return await asyncio.to_thread(self._request_once_sync, prompt)

    def _request_once_sync(self, prompt: str) -> LLMCallResult:
        started = time.perf_counter()
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.config.model,
            "temperature": TEMPERATURE,
            "messages": [{"role": "user", "content": prompt}],
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                response_text = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LLMError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise LLMError(str(exc)) from exc

        elapsed = time.perf_counter() - started
        try:
            data = json.loads(response_text)
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LLMError(f"Invalid OpenAI-compatible response: {response_text[:500]}") from exc
        return LLMCallResult(raw_response=content, elapsed_seconds=elapsed)

