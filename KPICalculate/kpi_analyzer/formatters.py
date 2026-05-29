from __future__ import annotations

from .json_utils import dumps_pretty
from .models import Dimension, LoadedInput, Member, MemberMaterial, WeekData


def format_project_context(data: LoadedInput) -> str:
    ctx = data.project_context
    project_scope = dumps_pretty(ctx.project_scope) if ctx.project_scope else "未提供"
    return (
        f"项目背景：\n{ctx.project_background}\n\n"
        f"结构化项目范围：\n{project_scope}\n\n"
        f"部门/岗位背景：\n{ctx.department_background}\n\n"
        f"补充评价说明：\n{ctx.analysis_note}\n\n"
        "注意：成员画像、沟通风格和工作习惯只能作为岗位背景参考，不能作为预设扣分依据；"
        "必须以本周周报、会议发言和项目目标贡献为主要判断依据。"
    )


def format_members(members: list[Member]) -> str:
    rows = []
    for member in members:
        rows.append(
            {
                "member_id": member.member_id,
                "name": member.name,
                "role": member.role,
                "responsibilities": member.responsibilities,
                "profile": {
                    "experience": member.profile.experience,
                    "skills": member.profile.skills,
                    "strengths": member.profile.strengths,
                    "weaknesses": member.profile.weaknesses,
                    "communication_style": member.profile.communication_style,
                    "persona_notes": member.profile.persona_notes,
                    "work_habits": member.profile.work_habits,
                },
            }
        )
    return dumps_pretty(rows)


def format_dimensions(dimensions: list[Dimension]) -> str:
    return dumps_pretty([item.as_dict() for item in dimensions])


def format_weekly_meeting(week: WeekData) -> str:
    meetings = []
    for meeting in week.meetings:
        meetings.append(
            {
                "title": meeting.title,
                "participants": meeting.participants,
                "speeches": [
                    {
                        "member_id": speech.member_id,
                        "member_name": speech.member_name,
                        "content": speech.content,
                    }
                    for speech in meeting.speeches
                ],
            }
        )
    return dumps_pretty(meetings)


def format_member_material(material: MemberMaterial) -> dict[str, object]:
    return {
        "member_id": material.member.member_id,
        "name": material.member.name,
        "role": material.member.role,
        "responsibilities": material.member.responsibilities,
        "weekly_report": material.report_content,
        "meeting_speeches": material.speech_contents,
    }
