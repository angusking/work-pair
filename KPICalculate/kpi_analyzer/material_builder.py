from __future__ import annotations

from .formatters import format_member_material
from .models import Member, MemberMaterial, WeekData


def build_member_material(member: Member, week: WeekData) -> MemberMaterial:
    report_content = ""
    for report in week.reports:
        if report.member_id == member.member_id:
            report_content = report.content
            break

    speeches: list[str] = []
    for meeting in week.meetings:
        for speech in meeting.speeches:
            if speech.member_id == member.member_id:
                speeches.append(speech.content)

    return MemberMaterial(member=member, report_content=report_content, speech_contents=speeches)


def pair_material_payload(material_a: MemberMaterial, material_b: MemberMaterial) -> dict[str, object]:
    return {
        "member_a_material": format_member_material(material_a),
        "member_b_material": format_member_material(material_b),
    }

