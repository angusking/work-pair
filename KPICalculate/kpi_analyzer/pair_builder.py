from __future__ import annotations

from itertools import combinations

from .material_builder import build_member_material
from .models import Member, Pair, WeekData


def build_pairs_for_week(week: WeekData, members: list[Member], mode: str, reviewer: str | None) -> list[Pair]:
    reviewer_or_mode = reviewer or mode
    pairs: list[Pair] = []
    for member_a, member_b in combinations(members, 2):
        pair_id = f"{week.week_id}__{reviewer_or_mode}__{member_a.member_id}__{member_b.member_id}"
        pairs.append(
            Pair(
                pair_id=pair_id,
                week_id=week.week_id,
                mode=mode,
                reviewer=reviewer,
                member_a=member_a,
                member_b=member_b,
                material_a=build_member_material(member_a, week),
                material_b=build_member_material(member_b, week),
            )
        )
    return pairs

