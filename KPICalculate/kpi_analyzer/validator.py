from __future__ import annotations

from .errors import InputValidationError
from .models import LoadedInput


def validate_input(data: LoadedInput) -> list[str]:
    warnings: list[str] = []
    errors: list[str] = []

    if not data.project_context.project_background.strip():
        warnings.append("项目背景缺失，只能执行直接比较。")
    if not data.project_context.department_background.strip():
        warnings.append("部门/岗位背景缺失，维度和评价官质量可能下降。")

    if not data.members:
        errors.append("members.json 中没有成员。")

    member_ids: set[str] = set()
    for member in data.members:
        if not member.member_id or not member.name or not member.role:
            warnings.append(f"成员最低字段不完整：{member}")
        if member.member_id in member_ids:
            errors.append(f"重复成员 ID：{member.member_id}")
        member_ids.add(member.member_id)

    if not data.weeks:
        errors.append("input/weeks 中没有周数据。")

    for week in data.weeks:
        if not week.week_id or not week.start_date or not week.end_date:
            errors.append(f"周数据缺少 week_id/start_date/end_date：{week}")
        for report in week.reports:
            if report.member_id not in member_ids:
                errors.append(f"{week.week_id} 周报成员 ID 不存在：{report.member_id}")
        for meeting in week.meetings:
            for speech in meeting.speeches:
                if speech.member_id not in member_ids:
                    errors.append(f"{week.week_id} 会议发言成员 ID 不存在：{speech.member_id}")
                if not speech.content.strip():
                    warnings.append(f"{week.week_id} 会议发言为空：{speech.member_id}")

    if errors:
        raise InputValidationError("; ".join(errors))
    return warnings


def has_complete_project_context(data: LoadedInput) -> bool:
    return bool(data.project_context.project_background.strip())


def has_complete_member_roles(data: LoadedInput) -> bool:
    return all(member.member_id and member.name and member.role for member in data.members)

