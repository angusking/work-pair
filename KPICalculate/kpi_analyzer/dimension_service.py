from __future__ import annotations

import asyncio
import json
from pathlib import Path

from .constants import MAX_RETRIES, MODE_DIMENSIONS, MODE_DIMENSIONS_REVIEWERS, TEMPERATURE, TIMEOUT_SECONDS
from .env_loader import LLMConfig
from .errors import KPIAnalyzerError, ParseError
from .formatters import format_members, format_project_context
from .json_utils import parse_json_object
from .jsonl_logger import JsonlLogger
from .llm_client import LLMClient
from .models import Dimension, LoadedInput
from .prompt_loader import PromptLoader
from .run_logger import RunLogger
from .utils import now_iso


def _parse_dimensions(raw_response: str) -> list[Dimension]:
    data = parse_json_object(raw_response)
    rows = data.get("dimensions")
    if not isinstance(rows, list):
        raise ParseError("Response JSON must contain a dimensions list.")
    dimensions: list[Dimension] = []
    for item in rows:
        if isinstance(item, str):
            dimensions.append(Dimension(name=item.strip()))
        elif isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            description = str(item.get("description", "")).strip()
            if name:
                dimensions.append(Dimension(name=name, description=description))
    if not dimensions:
        raise ParseError("No valid dimensions found.")
    return dimensions


class DimensionService:
    def __init__(
        self,
        llm_client: LLMClient,
        llm_config: LLMConfig,
        prompt_loader: PromptLoader,
        llm_logger: JsonlLogger,
        error_logger: JsonlLogger,
        run_logger: RunLogger,
        output_dir: Path,
        run_id: str,
    ):
        self.llm_client = llm_client
        self.llm_config = llm_config
        self.prompt_loader = prompt_loader
        self.llm_logger = llm_logger
        self.error_logger = error_logger
        self.run_logger = run_logger
        self.output_dir = output_dir
        self.run_id = run_id

    async def generate_for_user_selection(self, data: LoadedInput) -> list[Dimension]:
        dimensions = await self._generate(data, "dimension_generation.md", MODE_DIMENSIONS, required_count=None)
        print("\n大模型生成的绩效维度：")
        for idx, item in enumerate(dimensions, start=1):
            suffix = f" - {item.description}" if item.description else ""
            print(f"{idx}. {item.name}{suffix}")
        selected = self._read_user_selection(dimensions)
        self._save_dimensions(selected, "selected_by_user")
        return selected

    async def auto_select_for_reviewers(self, data: LoadedInput) -> list[Dimension]:
        dimensions = await self._generate(
            data,
            "dimension_auto_select_for_reviewers.md",
            MODE_DIMENSIONS_REVIEWERS,
            required_count=5,
        )
        self._save_dimensions(dimensions, "auto_selected_for_reviewers")
        return dimensions

    async def _generate(
        self,
        data: LoadedInput,
        template_name: str,
        mode: str,
        required_count: int | None,
    ) -> list[Dimension]:
        prompt = self.prompt_loader.render(
            template_name,
            {
                "project_context": format_project_context(data),
                "members": format_members(data.members),
            },
        )
        interaction_type = "dimension_generation"
        last_error: str | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            timestamp = now_iso()
            try:
                result = await self.llm_client.request_once(prompt)
                dimensions = _parse_dimensions(result.raw_response)
                if required_count is not None and len(dimensions) != required_count:
                    raise ParseError(f"Expected {required_count} dimensions, got {len(dimensions)}.")
                self.llm_logger.write(
                    {
                        "timestamp": timestamp,
                        "interaction_id": f"{interaction_type}_{timestamp}_{attempt}",
                        "run_id": self.run_id,
                        "type": interaction_type,
                        "mode": mode,
                        "prompt_template": template_name,
                        "pairs": [],
                        "request": {
                            "base_url": self.llm_config.base_url,
                            "model": self.llm_config.model,
                            "temperature": TEMPERATURE,
                            "timeout_seconds": TIMEOUT_SECONDS,
                            "attempt": attempt,
                        },
                        "rendered_prompt": prompt,
                        "raw_response": result.raw_response,
                        "parsed_response": {"dimensions": [item.as_dict() for item in dimensions]},
                        "elapsed_seconds": result.elapsed_seconds,
                        "success": True,
                        "error": None,
                    }
                )
                return dimensions
            except Exception as exc:  # noqa: BLE001 - logged and retried deliberately.
                last_error = str(exc)
                self.llm_logger.write(
                    {
                        "timestamp": timestamp,
                        "interaction_id": f"{interaction_type}_{timestamp}_{attempt}",
                        "run_id": self.run_id,
                        "type": interaction_type,
                        "mode": mode,
                        "prompt_template": template_name,
                        "pairs": [],
                        "request": {
                            "base_url": self.llm_config.base_url,
                            "model": self.llm_config.model,
                            "temperature": TEMPERATURE,
                            "timeout_seconds": TIMEOUT_SECONDS,
                            "attempt": attempt,
                        },
                        "rendered_prompt": prompt,
                        "raw_response": None,
                        "parsed_response": None,
                        "elapsed_seconds": None,
                        "success": False,
                        "error": last_error,
                    }
                )
                self.run_logger.warn(f"Dimension generation failed on attempt {attempt}: {last_error}")
                await asyncio.sleep(min(2 * attempt, 5))
        self.error_logger.write(
            {
                "timestamp": now_iso(),
                "run_id": self.run_id,
                "level": "ERROR",
                "stage": "dimension_generation",
                "message": last_error or "Unknown dimension generation error",
                "details": {"mode": mode, "template": template_name},
            }
        )
        raise KPIAnalyzerError(last_error or "Dimension generation failed.")

    def _read_user_selection(self, dimensions: list[Dimension]) -> list[Dimension]:
        while True:
            raw = input("请输入选择和排序后的维度编号（至少 3 个，例如 3,1,5）：").strip()
            try:
                indexes = [int(part.strip()) for part in raw.split(",") if part.strip()]
            except ValueError:
                print("输入格式错误，请输入逗号分隔的编号。")
                continue
            if len(indexes) < 3:
                print("至少选择 3 个维度。")
                continue
            if len(indexes) != len(set(indexes)):
                print("编号不能重复。")
                continue
            if any(index < 1 or index > len(dimensions) for index in indexes):
                print("存在无效编号。")
                continue
            return [dimensions[index - 1] for index in indexes]

    def _save_dimensions(self, dimensions: list[Dimension], source: str) -> None:
        path = self.output_dir / "selected_dimensions.json"
        payload = {"source": source, "dimensions": [item.as_dict() for item in dimensions]}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

