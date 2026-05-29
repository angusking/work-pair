from __future__ import annotations

import asyncio
import json
from pathlib import Path

from kpi_analyzer.comparison_runner import ComparisonRunner
from kpi_analyzer.constants import (
    CONCURRENCY,
    INPUT_DIR,
    MAX_PAIRS_PER_LLM_CALL,
    MAX_RETRIES,
    MODE_DIMENSIONS,
    MODE_DIMENSIONS_REVIEWERS,
    MODE_DIRECT,
    MODE_LABELS,
    MODE_REVIEWERS,
    OUTPUT_DIR,
    PROMPTS_DIR,
    TEMPERATURE,
    TIMEOUT_SECONDS,
)
from kpi_analyzer.dimension_service import DimensionService
from kpi_analyzer.env_loader import load_llm_config
from kpi_analyzer.errors import KPIAnalyzerError
from kpi_analyzer.input_loader import load_input
from kpi_analyzer.jsonl_logger import JsonlLogger
from kpi_analyzer.llm_client import LLMClient
from kpi_analyzer.models import Dimension
from kpi_analyzer.prompt_loader import PromptLoader
from kpi_analyzer.report_renderer import render_html, render_markdown
from kpi_analyzer.run_logger import RunLogger
from kpi_analyzer.scoring import score_results
from kpi_analyzer.utils import make_run_id, now_iso
from kpi_analyzer.validator import has_complete_member_roles, has_complete_project_context, validate_input


def choose_mode() -> str:
    choices = {
        "1": MODE_DIRECT,
        "2": MODE_DIMENSIONS,
        "3": MODE_REVIEWERS,
        "4": MODE_DIMENSIONS_REVIEWERS,
    }
    print("请选择分析模式：")
    print("1. 直接比较")
    print("2. 绩效维度比较")
    print("3. 评价官比较")
    print("4. 绩效维度 + 评价官比较")
    while True:
        raw = input("请输入 1/2/3/4：").strip()
        if raw in choices:
            return choices[raw]
        print("无效选择，请重新输入。")


async def async_main() -> int:
    run_id = make_run_id()
    output_root = Path(OUTPUT_DIR)
    output_dir = output_root / "runs" / run_id
    logs_dir = output_dir / "logs"
    reports_dir = output_dir / "reports"
    artifacts_dir = output_dir / "artifacts"
    for path in (logs_dir, reports_dir, artifacts_dir):
        path.mkdir(parents=True, exist_ok=True)

    run_logger = RunLogger(logs_dir / "run.log")
    llm_logger = JsonlLogger(logs_dir / "llm_interactions.jsonl")
    comparison_logger = JsonlLogger(logs_dir / "comparisons.jsonl")
    error_logger = JsonlLogger(logs_dir / "errors.jsonl")

    run_logger.info(f"Run started: {run_id}")
    print(f"Run: {run_id}")

    try:
        run_logger.info("Loading environment from .env")
        llm_config = load_llm_config(Path(".env"))
        run_logger.info(f"LLM provider configured: base_url={llm_config.base_url}, model={llm_config.model}")

        print("[1/6] Loading input ...", end=" ")
        run_logger.info("Loading input JSON")
        data = load_input(Path(INPUT_DIR))
        warnings = validate_input(data)
        for warning in warnings:
            run_logger.warn(warning)
        print("done")
        print(f"Input: {len(data.members)} members, {len(data.weeks)} weeks")
        run_logger.info(f"Loaded {len(data.members)} members")
        run_logger.info(f"Loaded {len(data.tasks)} final tasks")
        if data.weeks:
            run_logger.info(f"Loaded {len(data.weeks)} weeks: {data.weeks[0].week_id} to {data.weeks[-1].week_id}")

        mode = choose_mode()
        if mode != MODE_DIRECT and (not has_complete_project_context(data) or not has_complete_member_roles(data)):
            run_logger.warn("Input lacks project background or member roles; forcing direct mode.")
            print("项目背景或成员职位信息缺失，只能执行方式一：直接比较。")
            mode = MODE_DIRECT
        print(f"Mode: {MODE_LABELS[mode]}")
        run_logger.info(f"Selected mode: {mode}")

        prompt_loader = PromptLoader(Path(PROMPTS_DIR))
        llm_client = LLMClient(llm_config)
        dimensions: list[Dimension] = []

        dimension_service = DimensionService(
            llm_client=llm_client,
            llm_config=llm_config,
            prompt_loader=prompt_loader,
            llm_logger=llm_logger,
            error_logger=error_logger,
            run_logger=run_logger,
            output_dir=artifacts_dir,
            run_id=run_id,
        )

        if mode == MODE_DIMENSIONS:
            print("[2/6] Generating dimensions for user selection ...")
            dimensions = await dimension_service.generate_for_user_selection(data)
            run_logger.info(f"Selected {len(dimensions)} dimensions by user")
        elif mode == MODE_DIMENSIONS_REVIEWERS:
            print("[2/6] Generating job-focused dimensions ...", end=" ")
            dimensions = await dimension_service.auto_select_for_reviewers(data)
            print("done")
            run_logger.info("Auto-selected 5 job-focused dimensions")
        else:
            print("[2/6] Dimension step skipped")

        write_input_snapshot(artifacts_dir, data)
        write_run_snapshot(artifacts_dir, run_id, mode, data, llm_config, output_dir)

        print("[3/6] Building comparison batches ...")
        runner = ComparisonRunner(
            llm_client=llm_client,
            llm_config=llm_config,
            prompt_loader=prompt_loader,
            llm_logger=llm_logger,
            comparison_logger=comparison_logger,
            error_logger=error_logger,
            run_logger=run_logger,
            run_id=run_id,
        )
        results = await runner.run(data, mode, dimensions)

        print("[5/6] Scoring rankings ...", end=" ")
        summary = score_results(results, data.members)
        print("done")
        run_logger.info("Scoring completed")

        print("[6/6] Rendering reports ...", end=" ")
        markdown_path = render_markdown(reports_dir, run_id, mode, data, dimensions, results, summary)
        html_path = render_html(reports_dir, markdown_path)
        print("done")
        run_logger.info(f"Reports written: {markdown_path.name}, {html_path.name}")

        run_logger.info(f"Run completed: comparisons={summary.comparison_count}, errors={summary.error_count}")
        print("\nCompleted.")
        print(f"Report: {html_path}")
        print(f"Errors: {summary.error_count}")
        (output_root / "latest_run.txt").write_text(str(output_dir), encoding="utf-8")
        return 0
    except Exception as exc:  # noqa: BLE001 - top-level CLI boundary.
        run_logger.error(str(exc))
        error_logger.write(
            {
                "timestamp": now_iso(),
                "run_id": run_id,
                "level": "ERROR",
                "stage": "fatal",
                "message": str(exc),
                "details": {"type": exc.__class__.__name__},
            }
        )
        print(f"运行失败：{exc}")
        return 1


def write_run_snapshot(artifacts_dir: Path, run_id: str, mode: str, data, llm_config, run_dir: Path) -> None:
    payload = {
        "run_id": run_id,
        "started_at": now_iso(),
        "analysis_mode": mode,
        "input_dir": INPUT_DIR,
        "output_dir": str(run_dir),
        "member_count": len(data.members),
        "week_count": len(data.weeks),
        "task_count": len(data.tasks),
        "llm": {
            "base_url": llm_config.base_url,
            "model": llm_config.model,
        },
        "constants": {
            "concurrency": CONCURRENCY,
            "max_retries": MAX_RETRIES,
            "max_pairs_per_llm_call": MAX_PAIRS_PER_LLM_CALL,
            "timeout_seconds": TIMEOUT_SECONDS,
            "temperature": TEMPERATURE,
        },
    }
    (artifacts_dir / "run_snapshot.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_input_snapshot(artifacts_dir: Path, data) -> None:
    payload = {
        "project_context": {
            "project_background": data.project_context.project_background,
            "department_background": data.project_context.department_background,
            "analysis_note": data.project_context.analysis_note,
            "project_scope": data.project_context.project_scope,
        },
        "members": [
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
            for member in data.members
        ],
        "weeks": [
            {
                "week_id": week.week_id,
                "start_date": week.start_date,
                "end_date": week.end_date,
                "reports": [
                    {
                        "member_id": report.member_id,
                        "member_name": report.member_name,
                        "content": report.content,
                    }
                    for report in week.reports
                ],
                "meetings": [
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
                    for meeting in week.meetings
                ],
            }
            for week in data.weeks
        ],
        "tasks": [
            {
                "task_id": task.task_id,
                "title": task.title,
                "description": task.description,
                "owner_id": task.owner_id,
                "collaborators": task.collaborators,
                "dependencies": task.dependencies,
                "priority": task.priority,
                "status": task.status,
                "progress": task.progress,
                "due_date": task.due_date,
                "notes": task.notes,
            }
            for task in data.tasks
        ],
    }
    (artifacts_dir / "input_snapshot.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    try:
        return asyncio.run(async_main())
    except KeyboardInterrupt:
        print("用户中断。")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
