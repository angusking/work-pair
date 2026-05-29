from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProjectContext:
    project_background: str = ""
    department_background: str = ""
    analysis_note: str = ""
    project_scope: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemberProfile:
    experience: str = ""
    skills: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    communication_style: str = ""
    persona_notes: str = ""
    work_habits: str = ""


@dataclass
class Member:
    member_id: str
    name: str
    role: str
    responsibilities: str = ""
    profile: MemberProfile = field(default_factory=MemberProfile)

    def brief(self) -> dict[str, str]:
        return {"member_id": self.member_id, "name": self.name, "role": self.role}


@dataclass
class WeeklyReport:
    member_id: str
    member_name: str
    content: str


@dataclass
class Speech:
    member_id: str
    member_name: str
    content: str


@dataclass
class Meeting:
    title: str
    participants: list[str]
    speeches: list[Speech]


@dataclass
class WeekData:
    week_id: str
    start_date: str
    end_date: str
    reports: list[WeeklyReport]
    meetings: list[Meeting]


@dataclass
class Task:
    task_id: str
    title: str
    description: str = ""
    owner_id: str = ""
    collaborators: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    priority: str = ""
    status: str = ""
    progress: int | float | None = None
    due_date: str | None = None
    notes: str = ""


@dataclass
class LoadedInput:
    project_context: ProjectContext
    members: list[Member]
    weeks: list[WeekData]
    tasks: list[Task] = field(default_factory=list)


@dataclass
class MemberMaterial:
    member: Member
    report_content: str = ""
    speech_contents: list[str] = field(default_factory=list)

    @property
    def has_report(self) -> bool:
        return bool(self.report_content.strip())

    @property
    def has_speech(self) -> bool:
        return any(item.strip() for item in self.speech_contents)

    @property
    def is_missing(self) -> bool:
        return not self.has_report and not self.has_speech


@dataclass
class Pair:
    pair_id: str
    week_id: str
    mode: str
    reviewer: str | None
    member_a: Member
    member_b: Member
    material_a: MemberMaterial
    material_b: MemberMaterial


@dataclass
class ComparisonBatch:
    batch_id: str
    week: WeekData
    mode: str
    reviewer: str | None
    prompt_template: str
    pairs: list[Pair]


@dataclass
class Dimension:
    name: str
    description: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "description": self.description}


@dataclass
class ComparisonResult:
    week_id: str
    mode: str
    reviewer: str | None
    pair_id: str
    member_a: Member
    member_b: Member
    winner: str | None
    score_a: float | None
    score_b: float | None
    confidence: str | None = None
    reason: str | None = None
    called_llm: bool = False
    automatic_reason: str | None = None
    batch_id: str | None = None
    is_error: bool = False
    error: str | None = None

    def to_json(self, run_id: str, timestamp: str) -> dict[str, Any]:
        return {
            "timestamp": timestamp,
            "run_id": run_id,
            "week_id": self.week_id,
            "mode": self.mode,
            "reviewer": self.reviewer,
            "pair_id": self.pair_id,
            "member_a": self.member_a.brief(),
            "member_b": self.member_b.brief(),
            "winner": self.winner,
            "score_a": self.score_a,
            "score_b": self.score_b,
            "confidence": self.confidence,
            "reason": self.reason,
            "called_llm": self.called_llm,
            "automatic_reason": self.automatic_reason,
            "batch_id": self.batch_id,
            "is_error": self.is_error,
            "error": self.error,
        }


@dataclass
class RankingRow:
    member: Member
    score: float
    valid_matches: int
    rank: int


@dataclass
class ScoreSummary:
    weekly: dict[str, dict[str, list[RankingRow]]]
    total: dict[str, list[RankingRow]]
    comparison_count: int
    error_count: int
