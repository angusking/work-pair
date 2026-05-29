from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import (
    LoadedInput,
    Meeting,
    Member,
    MemberProfile,
    ProjectContext,
    Speech,
    Task,
    WeekData,
    WeeklyReport,
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_project_context(input_dir: Path) -> ProjectContext:
    data = _read_json(input_dir / "project_context.json")
    return ProjectContext(
        project_background=data.get("project_background", ""),
        department_background=data.get("department_background", ""),
        analysis_note=data.get("analysis_note", ""),
        project_scope=data.get("project_scope") or {},
    )


def load_members(input_dir: Path) -> list[Member]:
    rows = _read_json(input_dir / "members.json")
    members: list[Member] = []
    for row in rows:
        profile_data = row.get("profile") or {}
        profile = MemberProfile(
            experience=profile_data.get("experience", ""),
            skills=list(profile_data.get("skills") or []),
            strengths=list(profile_data.get("strengths") or []),
            weaknesses=list(profile_data.get("weaknesses") or []),
            communication_style=profile_data.get("communication_style", ""),
            persona_notes=profile_data.get("persona_notes", ""),
            work_habits=profile_data.get("work_habits", ""),
        )
        members.append(
            Member(
                member_id=row.get("member_id", ""),
                name=row.get("name", ""),
                role=row.get("role", ""),
                responsibilities=row.get("responsibilities", ""),
                profile=profile,
            )
        )
    return members


def load_weeks(input_dir: Path) -> list[WeekData]:
    weeks_dir = input_dir / "weeks"
    weeks: list[WeekData] = []
    for path in sorted(weeks_dir.glob("*.json"), key=lambda item: item.name):
        data = _read_json(path)
        reports = [
            WeeklyReport(
                member_id=row.get("member_id", ""),
                member_name=row.get("member_name", ""),
                content=row.get("content", ""),
            )
            for row in data.get("reports", [])
        ]
        meetings: list[Meeting] = []
        for meeting_data in data.get("meetings", []):
            speeches = [
                Speech(
                    member_id=row.get("member_id", ""),
                    member_name=row.get("member_name", ""),
                    content=row.get("content", ""),
                )
                for row in meeting_data.get("speeches", [])
            ]
            meetings.append(
                Meeting(
                    title=meeting_data.get("title", ""),
                    participants=list(meeting_data.get("participants") or []),
                    speeches=speeches,
                )
            )
        weeks.append(
            WeekData(
                week_id=data.get("week_id", ""),
                start_date=data.get("start_date", ""),
                end_date=data.get("end_date", ""),
                reports=reports,
                meetings=meetings,
            )
        )
    return sorted(weeks, key=lambda item: item.week_id)


def load_tasks(input_dir: Path) -> list[Task]:
    path = input_dir / "final_tasks.json"
    if not path.exists():
        return []
    rows = _read_json(path)
    tasks: list[Task] = []
    for row in rows:
        tasks.append(
            Task(
                task_id=row.get("task_id", ""),
                title=row.get("title", ""),
                description=row.get("description", ""),
                owner_id=row.get("owner_id", ""),
                collaborators=list(row.get("collaborators") or []),
                dependencies=list(row.get("dependencies") or []),
                priority=row.get("priority", ""),
                status=row.get("status", ""),
                progress=row.get("progress"),
                due_date=row.get("due_date"),
                notes=row.get("notes", ""),
            )
        )
    return tasks


def load_input(input_dir: Path) -> LoadedInput:
    return LoadedInput(
        project_context=load_project_context(input_dir),
        members=load_members(input_dir),
        weeks=load_weeks(input_dir),
        tasks=load_tasks(input_dir),
    )
