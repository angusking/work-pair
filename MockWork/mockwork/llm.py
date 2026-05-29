from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from dotenv import load_dotenv

from .json_utils import extract_json_object


class LLMClient(Protocol):
    model_name: str

    def json(self, system: str, prompt: str) -> Any:
        ...

    def text(self, system: str, prompt: str) -> str:
        ...


@dataclass
class OpenAICompatibleLLM:
    model_name: str
    max_retries: int = 3
    temperature: float = 0.7
    log_dir: Path | None = None
    auto_log: bool = False

    @classmethod
    def from_env(cls, max_retries: int = 3, log_dir: Path | None = None) -> "OpenAICompatibleLLM":
        load_dotenv()
        model = os.getenv("OPENAI_MODEL")
        api_key = os.getenv("OPENAI_API_KEY")
        if not model:
            raise RuntimeError("OPENAI_MODEL is not set. Copy .env.example to .env and fill it in.")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set. Copy .env.example to .env and fill it in.")
        return cls(model_name=model, max_retries=max_retries, log_dir=log_dir)

    def _chat(self, system: str, prompt: str) -> str:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage

        load_dotenv()
        client = ChatOpenAI(
            model=self.model_name,
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL"),
            temperature=self.temperature,
        )

        last_exc: Exception | None = None
        response_text = ""
        
        for attempt in range(1, self.max_retries + 1):
            try:
                result = client.invoke([SystemMessage(content=system), HumanMessage(content=prompt)])
                response_text = str(result.content)
                if self.auto_log:
                    self._log_interaction(system, prompt, response_text)
                return response_text
            except Exception as exc:  # pragma: no cover - depends on provider/network
                last_exc = exc
                error_msg = str(exc)
                if self.auto_log:
                    self._log_interaction(system, prompt, "", error=error_msg)
                if attempt < self.max_retries:
                    time.sleep(min(2**attempt, 8))
        
        raise RuntimeError(f"LLM call failed after {self.max_retries} retries: {last_exc}") from last_exc

    def _log_interaction(self, system: str, prompt: str, response: str = "", error: str | None = None) -> None:
        """Log LLM interaction to file."""
        from .io import log_llm_interaction
        
        log_llm_interaction(
            run_dir=self.log_dir,
            source="llm_client",
            system=system,
            prompt=prompt,
            response=response,
            error=error,
        )

    def json(self, system: str, prompt: str) -> Any:
        last_exc: Exception | None = None
        current_prompt = prompt
        for attempt in range(1, self.max_retries + 1):
            response_text = self._chat(system, current_prompt)
            try:
                return extract_json_object(response_text)
            except Exception as exc:
                last_exc = exc
                if self.auto_log:
                    self._log_interaction(system, current_prompt, response_text, error=str(exc))
                if attempt < self.max_retries:
                    current_prompt = (
                        prompt
                        + "\n\n上一次输出无法被解析为合法 JSON。请重新输出，要求："
                        + "\n- 只输出一个合法 JSON 对象或数组"
                        + "\n- 必须使用英文双引号"
                        + "\n- 不要使用 Python 字典格式"
                        + "\n- 不要添加 Markdown、注释或解释"
                        + f"\n解析错误：{exc}"
                    )
                    time.sleep(min(2**attempt, 8))
        raise RuntimeError(f"LLM JSON parse failed after {self.max_retries} attempts: {last_exc}") from last_exc

    def text(self, system: str, prompt: str) -> str:
        return self._chat(system, prompt).strip()
