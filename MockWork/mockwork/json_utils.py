from __future__ import annotations

import ast
import json
import re
from typing import Any


def extract_json_object(text: str) -> Any:
    """Parse a JSON response, tolerating Markdown fences and surrounding text."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    try:
        return ast.literal_eval(cleaned)
    except (ValueError, SyntaxError):
        pass

    starts = [idx for idx in (cleaned.find("{"), cleaned.find("[")) if idx >= 0]
    if not starts:
        raise ValueError("LLM response did not contain JSON")

    start = min(starts)
    last_exc: Exception | None = None
    for end in range(len(cleaned), start, -1):
        candidate = cleaned[start:end].strip()
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_exc = exc
        try:
            return ast.literal_eval(candidate)
        except (ValueError, SyntaxError) as exc:
            last_exc = exc

    raise ValueError(f"LLM response did not contain parseable JSON: {last_exc}") from last_exc


def dumps_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)
