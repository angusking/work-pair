from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


TEMPLATE_DIR = Path(__file__).resolve().parent / "prompt_templates"


@lru_cache(maxsize=None)
def load_template(name: str) -> str:
    return (TEMPLATE_DIR / name).read_text(encoding="utf-8").strip()


def as_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def render_template(name: str, **values: Any) -> str:
    text = load_template(name)
    for key, value in values.items():
        text = text.replace(f"{{{{{key}}}}}", str(value))
    return text.strip()


JSON_RULE = load_template("json_rule.txt")


def system_prompt(name: str) -> str:
    return render_template(f"system_{name}.txt", json_rule=JSON_RULE)


def member_generation_prompt(background: str, member_count: int, org_structure: str) -> str:
    return render_template(
        "member_generation.md",
        background=background,
        member_count=member_count,
        org_structure=org_structure or "未提供，请自行设计合理团队结构。",
    )


def task_generation_prompt(background: str, members: list[dict[str, Any]]) -> str:
    return render_template(
        "task_generation.md",
        background=background,
        members=as_json(members),
    )


def project_scope_evaluation_prompt(brief: str, duration_days: int, workdays_count: int) -> str:
    return render_template(
        "project_scope_evaluation.md",
        brief=brief,
        duration_days=duration_days,
        workdays_count=workdays_count,
    )


def shared_week_prompt(
    background: str,
    week: dict[str, Any],
    members: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    project_memory: list[str],
    is_final_week: bool,
) -> str:
    return render_template(
        "shared_week.md",
        week_id=week["week_id"],
        week_start=week["start_date"],
        week_end=week["end_date"],
        background=background,
        members=as_json(members),
        tasks=as_json(tasks),
        project_memory=as_json(project_memory[-8:]),
        is_final_week=is_final_week,
    )


def weekly_report_prompt(
    background: str,
    week: dict[str, Any],
    member: dict[str, Any],
    tasks: list[dict[str, Any]],
    week_context: dict[str, Any],
    recent_report: dict[str, Any] | None,
    is_final_week: bool,
) -> str:
    return render_template(
        "weekly_report.md",
        member_name=member["name"],
        week_id=week["week_id"],
        week_start=week["start_date"],
        week_end=week["end_date"],
        background=background,
        member=as_json(member),
        tasks=as_json(tasks),
        week_context=as_json(week_context),
        recent_report=as_json(recent_report or {}),
        is_final_week=is_final_week,
    )


def weekly_meeting_turn_prompt(
    background: str,
    week: dict[str, Any],
    speaker: dict[str, Any],
    all_issues: list[dict[str, Any]],
    speaker_issues: list[dict[str, Any]],
    related_tasks: list[dict[str, Any]],
    transcript: list[dict[str, str]],
    turn_index: int,
    max_turns: int,
    is_final_week: bool,
) -> str:
    return render_template(
        "weekly_meeting_turn.md",
        week_id=week["week_id"],
        week_start=week["start_date"],
        week_end=week["end_date"],
        background=background,
        speaker=as_json(speaker),
        all_issues=as_json(all_issues),
        speaker_issues=as_json(speaker_issues),
        related_tasks=as_json(related_tasks),
        transcript=as_json(transcript),
        turn_index=turn_index,
        max_turns=max_turns,
        is_final_week=is_final_week,
    )


def member_summary_prompt(
    background: str,
    member: dict[str, Any],
    member_events: list[dict[str, Any]],
) -> str:
    return render_template(
        "member_summary.md",
        member_name=member["name"],
        background=background,
        member=as_json(member),
        member_events=as_json(member_events[-80:]),
    )
