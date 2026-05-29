from __future__ import annotations

from collections import defaultdict

from .constants import MODE_DIMENSIONS_REVIEWERS, MODE_REVIEWERS
from .models import ComparisonResult, Member, RankingRow, ScoreSummary


OVERALL_KEY = "overall"


def _context_key(result: ComparisonResult) -> str:
    return result.reviewer or OVERALL_KEY


def _empty_member_stats(members: list[Member]) -> dict[str, dict[str, float | int]]:
    return {member.member_id: {"score": 0.0, "valid_matches": 0} for member in members}


def _rank_rows(stats: dict[str, dict[str, float | int]], member_by_id: dict[str, Member]) -> list[RankingRow]:
    raw_rows = [
        (member_id, float(values["score"]), int(values["valid_matches"]))
        for member_id, values in stats.items()
        if member_id in member_by_id
    ]
    raw_rows.sort(key=lambda item: (-item[1], member_by_id[item[0]].name))
    rows: list[RankingRow] = []
    previous_score: float | None = None
    previous_rank = 0
    for index, (member_id, score, valid_matches) in enumerate(raw_rows, start=1):
        if previous_score is not None and score == previous_score:
            rank = previous_rank
        else:
            rank = index
        rows.append(RankingRow(member=member_by_id[member_id], score=score, valid_matches=valid_matches, rank=rank))
        previous_score = score
        previous_rank = rank
    return rows


def _score_value(value: object) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def score_results(results: list[ComparisonResult], members: list[Member]) -> ScoreSummary:
    member_by_id = {member.member_id: member for member in members}
    weekly_stats: dict[str, dict[str, dict[str, dict[str, float | int]]]] = defaultdict(dict)
    total_stats: dict[str, dict[str, dict[str, float | int]]] = {}

    for result in results:
        if result.is_error or result.score_a is None or result.score_b is None:
            continue
        key = _context_key(result)
        if key not in weekly_stats[result.week_id]:
            weekly_stats[result.week_id][key] = _empty_member_stats(members)
        if key not in total_stats:
            total_stats[key] = _empty_member_stats(members)

        for stats in (weekly_stats[result.week_id][key], total_stats[key]):
            stats[result.member_a.member_id]["score"] = (
                float(stats[result.member_a.member_id]["score"]) + _score_value(result.score_a)
            )
            stats[result.member_a.member_id]["valid_matches"] = int(stats[result.member_a.member_id]["valid_matches"]) + 1
            stats[result.member_b.member_id]["score"] = (
                float(stats[result.member_b.member_id]["score"]) + _score_value(result.score_b)
            )
            stats[result.member_b.member_id]["valid_matches"] = int(stats[result.member_b.member_id]["valid_matches"]) + 1

        if result.mode in (MODE_REVIEWERS, MODE_DIMENSIONS_REVIEWERS):
            if OVERALL_KEY not in weekly_stats[result.week_id]:
                weekly_stats[result.week_id][OVERALL_KEY] = _empty_member_stats(members)
            if OVERALL_KEY not in total_stats:
                total_stats[OVERALL_KEY] = _empty_member_stats(members)
            for stats in (weekly_stats[result.week_id][OVERALL_KEY], total_stats[OVERALL_KEY]):
                stats[result.member_a.member_id]["score"] = (
                    float(stats[result.member_a.member_id]["score"]) + _score_value(result.score_a)
                )
                stats[result.member_a.member_id]["valid_matches"] = (
                    int(stats[result.member_a.member_id]["valid_matches"]) + 1
                )
                stats[result.member_b.member_id]["score"] = (
                    float(stats[result.member_b.member_id]["score"]) + _score_value(result.score_b)
                )
                stats[result.member_b.member_id]["valid_matches"] = (
                    int(stats[result.member_b.member_id]["valid_matches"]) + 1
                )

    weekly_rankings: dict[str, dict[str, list[RankingRow]]] = {}
    for week_id, contexts in weekly_stats.items():
        weekly_rankings[week_id] = {
            key: _rank_rows(stats, member_by_id)
            for key, stats in sorted(contexts.items(), key=lambda item: item[0])
        }
    total_rankings = {
        key: _rank_rows(stats, member_by_id)
        for key, stats in sorted(total_stats.items(), key=lambda item: item[0])
    }

    return ScoreSummary(
        weekly=dict(sorted(weekly_rankings.items(), key=lambda item: item[0])),
        total=total_rankings,
        comparison_count=len(results),
        error_count=sum(1 for result in results if result.is_error),
    )
