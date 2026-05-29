from __future__ import annotations

from pathlib import Path


class PromptLoader:
    def __init__(self, prompts_dir: Path):
        self.prompts_dir = prompts_dir

    def load(self, template_name: str) -> str:
        return (self.prompts_dir / template_name).read_text(encoding="utf-8")

    def render(self, template_name: str, values: dict[str, str]) -> str:
        prompt = self.load(template_name)
        for key, value in values.items():
            prompt = prompt.replace("{{" + key + "}}", value)
        return prompt

