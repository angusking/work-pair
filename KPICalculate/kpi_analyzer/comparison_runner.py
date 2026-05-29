from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any

from .constants import (
    CONCURRENCY,
    MAX_PAIRS_PER_LLM_CALL,
    MAX_RETRIES,
    MODE_DIMENSIONS,
    MODE_DIMENSIONS_REVIEWERS,
    MODE_DIRECT,
    MODE_REVIEWERS,
    REVIEWER_BUSINESS,
    REVIEWER_HRBP,
    TEMPERATURE,
    TIMEOUT_SECONDS,
)
from .env_loader import LLMConfig
from .formatters import (
    format_dimensions,
    format_member_material,
    format_members,
    format_project_context,
    format_weekly_meeting,
)
from .json_utils import dumps_pretty, parse_json_object
from .jsonl_logger import JsonlLogger
from .llm_client import LLMClient
from .models import ComparisonBatch, ComparisonResult, Dimension, LoadedInput, Pair, WeekData
from .pair_builder import build_pairs_for_week
from .prompt_loader import PromptLoader
from .run_logger import RunLogger
from .utils import now_iso


def reviewer_label(reviewer: str | None) -> str:
    if reviewer == REVIEWER_HRBP:
        return "HRBP"
    if reviewer == REVIEWER_BUSINESS:
        return "业务主管"
    return "综合"


def _chunks(items: list[Pair], size: int) -> Iterable[list[Pair]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


class ComparisonRunner:
    def __init__(
        self,
        llm_client: LLMClient,
        llm_config: LLMConfig,
        prompt_loader: PromptLoader,
        llm_logger: JsonlLogger,
        comparison_logger: JsonlLogger,
        error_logger: JsonlLogger,
        run_logger: RunLogger,
        run_id: str,
    ):
        self.llm_client = llm_client
        self.llm_config = llm_config
        self.prompt_loader = prompt_loader
        self.llm_logger = llm_logger
        self.comparison_logger = comparison_logger
        self.error_logger = error_logger
        self.run_logger = run_logger
        self.run_id = run_id
        self._extra_rows_by_pair_id: dict[str, dict[str, Any]] = {}

    async def run(self, data: LoadedInput, mode: str, dimensions: list[Dimension]) -> list[ComparisonResult]:
        contexts = self._contexts_for_mode(mode)
        all_results: list[ComparisonResult] = []
        batches: list[ComparisonBatch] = []

        self.run_logger.info("Building comparison pairs")
        for week in data.weeks:
            for reviewer in contexts:
                pairs = build_pairs_for_week(week, data.members, mode, reviewer)
                automatic, llm_pairs = self._split_automatic_pairs(pairs)
                for result in automatic:
                    self._log_comparison(result)
                all_results.extend(automatic)
                template = self._template_for(mode, reviewer)
                for batch_index, pair_chunk in enumerate(_chunks(llm_pairs, MAX_PAIRS_PER_LLM_CALL), start=1):
                    reviewer_or_mode = reviewer or mode
                    batch_id = f"{week.week_id}__{reviewer_or_mode}__batch_{batch_index:03d}"
                    batches.append(
                        ComparisonBatch(
                            batch_id=batch_id,
                            week=week,
                            mode=mode,
                            reviewer=reviewer,
                            prompt_template=template,
                            pairs=pair_chunk,
                        )
                    )
                self.run_logger.info(
                    f"Week {week.week_id} / {reviewer_label(reviewer)}: "
                    f"{len(pairs)} pairs, {len(automatic)} automatic, {len(llm_pairs)} require LLM"
                )

        self.run_logger.info(f"Created {len(batches)} LLM batches with concurrency={CONCURRENCY}")
        print(f"[4/6] Running LLM batches with concurrency={CONCURRENCY}")
        completed = 0
        semaphore = asyncio.Semaphore(CONCURRENCY)

        async def run_one(batch: ComparisonBatch) -> list[ComparisonResult]:
            async with semaphore:
                return await self._run_batch(batch, data, dimensions)

        tasks = [asyncio.create_task(run_one(batch)) for batch in batches]
        for task in asyncio.as_completed(tasks):
            batch_results = await task
            completed += 1
            valid_count = sum(1 for item in batch_results if not item.is_error)
            error_count = sum(1 for item in batch_results if item.is_error)
            print(f"      completed {completed}/{len(batches)}: valid={valid_count} errors={error_count}")
            all_results.extend(batch_results)

        return all_results

    def _contexts_for_mode(self, mode: str) -> list[str | None]:
        if mode in (MODE_DIRECT, MODE_DIMENSIONS):
            return [None]
        if mode in (MODE_REVIEWERS, MODE_DIMENSIONS_REVIEWERS):
            return [REVIEWER_HRBP, REVIEWER_BUSINESS]
        raise ValueError(f"Unknown analysis mode: {mode}")

    def _template_for(self, mode: str, reviewer: str | None) -> str:
        if mode == MODE_DIRECT:
            return "compare_direct_batch.md"
        if mode == MODE_DIMENSIONS:
            return "compare_by_dimensions_batch.md"
        if mode == MODE_REVIEWERS and reviewer == REVIEWER_HRBP:
            return "compare_as_hrbp_batch.md"
        if mode == MODE_REVIEWERS and reviewer == REVIEWER_BUSINESS:
            return "compare_as_business_lead_batch.md"
        if mode == MODE_DIMENSIONS_REVIEWERS:
            return "compare_by_dimensions_as_reviewer_batch.md"
        raise ValueError(f"Unsupported mode/reviewer: {mode}/{reviewer}")

    def _split_automatic_pairs(self, pairs: list[Pair]) -> tuple[list[ComparisonResult], list[Pair]]:
        automatic: list[ComparisonResult] = []
        llm_pairs: list[Pair] = []
        for pair in pairs:
            a_missing = pair.material_a.is_missing
            b_missing = pair.material_b.is_missing
            if a_missing and b_missing:
                automatic.append(self._automatic_result(pair, "TIE", "both_members_missing_report_and_speech"))
            elif a_missing:
                automatic.append(self._automatic_result(pair, "B", "member_a_missing_report_and_speech"))
            elif b_missing:
                automatic.append(self._automatic_result(pair, "A", "member_b_missing_report_and_speech"))
            else:
                llm_pairs.append(pair)
        return automatic, llm_pairs

    def _automatic_result(self, pair: Pair, winner: str, reason: str) -> ComparisonResult:
        score_a, score_b = self._scores_for_winner(winner)
        return ComparisonResult(
            week_id=pair.week_id,
            mode=pair.mode,
            reviewer=pair.reviewer,
            pair_id=pair.pair_id,
            member_a=pair.member_a,
            member_b=pair.member_b,
            winner=winner,
            score_a=score_a,
            score_b=score_b,
            reason=f"自动判定：{reason}",
            called_llm=False,
            automatic_reason=reason,
        )

    async def _run_batch(
        self,
        batch: ComparisonBatch,
        data: LoadedInput,
        dimensions: list[Dimension],
    ) -> list[ComparisonResult]:
        self.run_logger.info(f"Batch started: {batch.batch_id}, pairs={len(batch.pairs)}")
        prompt = self._render_batch_prompt(batch, data, dimensions)
        last_error: str | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            timestamp = now_iso()
            try:
                response = await self.llm_client.request_once(prompt)
                parsed = parse_json_object(response.raw_response)
                results = self._parse_batch_results(batch, parsed)
                valid_count = sum(1 for item in results if not item.is_error)
                error_count = sum(1 for item in results if item.is_error)
                self.llm_logger.write(
                    self._llm_log_record(
                        timestamp,
                        batch,
                        prompt,
                        response.raw_response,
                        parsed,
                        response.elapsed_seconds,
                        True,
                        None,
                        attempt,
                    )
                )
                for result in results:
                    self._log_comparison(result)
                    if result.is_error:
                        self._log_error_for_result(result, "comparison_parse")
                if error_count:
                    self.run_logger.warn(
                        f"Batch partial errors: {batch.batch_id}, valid={valid_count}, errors={error_count}"
                    )
                else:
                    self.run_logger.info(f"Batch completed: {batch.batch_id}, valid={valid_count}, errors=0")
                return results
            except Exception as exc:  # noqa: BLE001 - logged and retried deliberately.
                last_error = str(exc)
                self.llm_logger.write(
                    self._llm_log_record(timestamp, batch, prompt, None, None, None, False, last_error, attempt)
                )
                self.run_logger.warn(f"Batch failed: {batch.batch_id}, attempt={attempt}, error={last_error}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(min(2 * attempt, 5))

        results = [
            ComparisonResult(
                week_id=pair.week_id,
                mode=pair.mode,
                reviewer=pair.reviewer,
                pair_id=pair.pair_id,
                member_a=pair.member_a,
                member_b=pair.member_b,
                winner=None,
                score_a=None,
                score_b=None,
                called_llm=True,
                batch_id=batch.batch_id,
                is_error=True,
                error=last_error or "Batch failed",
            )
            for pair in batch.pairs
        ]
        for result in results:
            self._log_comparison(result)
            self._log_error_for_result(result, "batch_failed")
        self.run_logger.error(f"Batch failed permanently: {batch.batch_id}, pairs={len(batch.pairs)}")
        return results

    def _render_batch_prompt(
        self,
        batch: ComparisonBatch,
        data: LoadedInput,
        dimensions: list[Dimension],
    ) -> str:
        pairs_payload = []
        for pair in batch.pairs:
            pairs_payload.append(
                {
                    "pair_id": pair.pair_id,
                    "a": pair.member_a.member_id,
                    "b": pair.member_b.member_id,
                    "member_a": format_member_material(pair.material_a),
                    "member_b": format_member_material(pair.material_b),
                }
            )
        return self.prompt_loader.render(
            batch.prompt_template,
            {
                "project_context": format_project_context(data),
                "department_context": data.project_context.department_background,
                "analysis_note": data.project_context.analysis_note,
                "members": format_members(data.members),
                "week_id": batch.week.week_id,
                "week_range": f"{batch.week.start_date} 至 {batch.week.end_date}",
                "weekly_meeting": format_weekly_meeting(batch.week),
                "pairs_json": dumps_pretty(pairs_payload),
                "dimensions": format_dimensions(dimensions),
                "reviewer_role": reviewer_label(batch.reviewer),
            },
        )

    def _parse_batch_results(self, batch: ComparisonBatch, parsed: dict[str, Any]) -> list[ComparisonResult]:
        rows = parsed.get("comparisons")
        if not isinstance(rows, list):
            raise ValueError("Response must contain comparisons list.")

        expected = {pair.pair_id: pair for pair in batch.pairs}
        seen: set[str] = set()
        row_by_pair: dict[str, dict[str, Any]] = {}
        duplicate_ids: set[str] = set()
        extra_rows: list[dict[str, Any]] = []

        for row in rows:
            if not isinstance(row, dict):
                continue
            pair_id = str(row.get("pair_id", "")).strip()
            if pair_id not in expected:
                extra_rows.append(row)
                if pair_id and pair_id not in self._extra_rows_by_pair_id:
                    self._extra_rows_by_pair_id[pair_id] = row
                continue
            if pair_id in seen:
                duplicate_ids.add(pair_id)
                continue
            seen.add(pair_id)
            row_by_pair[pair_id] = row

        if extra_rows:
            self.run_logger.warn(
                f"Batch returned {len(extra_rows)} extra comparison rows outside current batch: {batch.batch_id}"
            )

        results: list[ComparisonResult] = []
        for pair_id, pair in expected.items():
            row = row_by_pair.get(pair_id)
            if row is None and pair_id in self._extra_rows_by_pair_id:
                row = self._extra_rows_by_pair_id.pop(pair_id)
                self.run_logger.warn(f"Recovered pair from earlier extra row: {pair_id}")
            if row is None:
                results.append(self._error_result(pair, batch.batch_id, "Missing comparison result for pair"))
                continue
            if pair_id in duplicate_ids:
                self.run_logger.warn(f"Duplicate comparison result ignored, using first row: {pair_id}")
            winner = str(row.get("winner", "")).strip().upper()
            confidence = str(row.get("confidence", "")).strip().lower() or None
            reason = str(row.get("reason", "")).strip() or None
            if winner not in {"A", "B", "TIE"}:
                results.append(self._error_result(pair, batch.batch_id, f"Invalid winner: {winner}"))
                continue
            if row.get("a") != pair.member_a.member_id or row.get("b") != pair.member_b.member_id:
                self.run_logger.warn(f"Returned a/b fields do not match pair_id; pair_id accepted: {pair_id}")
            score_a, score_b = self._scores_for_winner(winner)
            results.append(
                ComparisonResult(
                    week_id=pair.week_id,
                    mode=pair.mode,
                    reviewer=pair.reviewer,
                    pair_id=pair.pair_id,
                    member_a=pair.member_a,
                    member_b=pair.member_b,
                    winner=winner,
                    score_a=score_a,
                    score_b=score_b,
                    confidence=confidence,
                    reason=reason,
                    called_llm=True,
                    batch_id=batch.batch_id,
                )
            )
        return results

    def _error_result(self, pair: Pair, batch_id: str, message: str) -> ComparisonResult:
        return ComparisonResult(
            week_id=pair.week_id,
            mode=pair.mode,
            reviewer=pair.reviewer,
            pair_id=pair.pair_id,
            member_a=pair.member_a,
            member_b=pair.member_b,
            winner=None,
            score_a=None,
            score_b=None,
            called_llm=True,
            batch_id=batch_id,
            is_error=True,
            error=message,
        )

    def _scores_for_winner(self, winner: str) -> tuple[float, float]:
        if winner == "A":
            return 1.0, 0.0
        if winner == "B":
            return 0.0, 1.0
        return 0.5, 0.5

    def _llm_log_record(
        self,
        timestamp: str,
        batch: ComparisonBatch,
        prompt: str,
        raw_response: str | None,
        parsed_response: dict[str, Any] | None,
        elapsed_seconds: float | None,
        success: bool,
        error: str | None,
        attempt: int,
    ) -> dict[str, Any]:
        return {
            "timestamp": timestamp,
            "interaction_id": f"{batch.batch_id}__attempt_{attempt}",
            "run_id": self.run_id,
            "type": "batch_comparison",
            "mode": batch.mode,
            "reviewer": batch.reviewer,
            "week_id": batch.week.week_id,
            "batch_id": batch.batch_id,
            "prompt_template": batch.prompt_template,
            "pairs": [
                {"pair_id": pair.pair_id, "a": pair.member_a.member_id, "b": pair.member_b.member_id}
                for pair in batch.pairs
            ],
            "request": {
                "base_url": self.llm_config.base_url,
                "model": self.llm_config.model,
                "temperature": TEMPERATURE,
                "timeout_seconds": TIMEOUT_SECONDS,
                "attempt": attempt,
            },
            "rendered_prompt": prompt,
            "raw_response": raw_response,
            "parsed_response": parsed_response,
            "elapsed_seconds": elapsed_seconds,
            "success": success,
            "error": error,
        }

    def _log_comparison(self, result: ComparisonResult) -> None:
        self.comparison_logger.write(result.to_json(self.run_id, now_iso()))

    def _log_error_for_result(self, result: ComparisonResult, stage: str) -> None:
        self.error_logger.write(
            {
                "timestamp": now_iso(),
                "run_id": self.run_id,
                "level": "ERROR",
                "stage": stage,
                "week_id": result.week_id,
                "reviewer": result.reviewer,
                "batch_id": result.batch_id,
                "pair_id": result.pair_id,
                "message": result.error,
                "details": {
                    "member_a": result.member_a.brief(),
                    "member_b": result.member_b.brief(),
                },
            }
        )
