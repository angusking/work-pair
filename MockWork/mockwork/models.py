from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Literal, TypedDict


@dataclass
class MemberProfile:
    member_id: str
    name: str
    role: str
    skills: list[str]
    experience: str
    communication_style: str
    strengths: list[str]
    weaknesses: list[str]
    work_habits: str
    persona_notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Task:
    task_id: str
    title: str
    description: str
    owner_id: str
    collaborators: list[str] = field(default_factory=list)
    status: Literal["todo", "in_progress", "blocked", "done"] = "todo"
    progress: int = 0
    priority: Literal["low", "medium", "high"] = "medium"
    due_date: str | None = None
    dependencies: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RunConfig:
    run_id: str
    start_date: date
    end_date: date
    model_name: str
    language: str = "中文"
    max_conversation_turns: int = 6
    max_retries: int = 3

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["start_date"] = self.start_date.isoformat()
        data["end_date"] = self.end_date.isoformat()
        return data


class GraphState(TypedDict, total=False):
    project_background: str
    members: list[dict[str, Any]]
    tasks: list[dict[str, Any]]
    run_config: dict[str, Any]
    run_dir: str
    project_scope: dict[str, Any]
    workdays: list[str]
    workweeks: list[dict[str, Any]]
    events: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    latest_reports: dict[str, dict[str, Any]]
    project_memory: list[str]
    carryover_weekly_issues: list[dict[str, Any]]
    weekly_stats: dict[str, dict[str, Any]]
