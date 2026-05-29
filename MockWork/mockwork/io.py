from __future__ import annotations

import json
import re
import threading
from html import escape
from datetime import datetime
from pathlib import Path
from typing import Any

from .json_utils import dumps_json


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INIT_DIR = PROJECT_ROOT / "init"
RUNS_DIR = PROJECT_ROOT / "runs"
BACKGROUND_FILE = INIT_DIR / "project_background.md"
MEMBERS_FILE = INIT_DIR / "members.md"
TASKS_FILE = INIT_DIR / "tasks.md"
PROJECT_SCOPE_FILE = INIT_DIR / "project_scope.json"
INIT_LLM_LOG_FILE = INIT_DIR / "llm_interactions.jsonl"
_JSONL_LOCK = threading.Lock()


def ensure_directories() -> None:
    INIT_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)


def has_initialized_project() -> bool:
    return BACKGROUND_FILE.exists() and MEMBERS_FILE.exists() and TASKS_FILE.exists()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps_json(data) + "\n", encoding="utf-8")


def append_jsonl(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _JSONL_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(dumps_json(event) + "\n")


def create_run_dir(run_id: str | None = None) -> Path:
    ensure_directories()
    resolved = run_id or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir = RUNS_DIR / resolved
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def write_run_metadata(run_dir: Path, metadata: dict[str, Any]) -> None:
    write_json(run_dir / "run_metadata.json", metadata)


def write_markdown_event(run_dir: Path, event: dict[str, Any]) -> None:
    event_type = event.get("event_type", "event")
    date = event.get("date", "unknown-date")
    path = run_dir / "work_records.md"
    with _JSONL_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(render_event_markdown(date, event_type, event))


def render_event_markdown(date: str, event_type: str, event: dict[str, Any]) -> str:
    title_by_type = {
        "daily_report": "日报",
        "weekly_report": "周报",
        "task_update": "任务推进",
        "conversation": "成员协商",
        "daily_meeting": "项目日会",
        "weekly_meeting": "周会纪要",
        "member_summary": "成员周期汇总",
        "run_error": "生成错误",
    }
    title = title_by_type.get(event_type, event_type)
    lines = [f"\n## {date} - {title}\n"]

    if event_type in {"daily_report", "weekly_report"}:
        lines.append(f"**成员**：{event.get('member_name', event.get('member_id', ''))}\n")
    if event.get("week_id"):
        lines.append(
            f"**周期**：{event.get('week_id')}（{event.get('week_start', '')} 至 {event.get('week_end', '')}）\n"
        )
    if event.get("task_ids"):
        lines.append(f"**相关任务**：{', '.join(event['task_ids'])}\n")
    if event.get("member_ids"):
        lines.append(f"**相关成员**：{', '.join(event['member_ids'])}\n")

    content = event.get("content") or event.get("summary") or ""
    if isinstance(content, list):
        content = "\n".join(f"- {item}" for item in content)
    lines.append(str(content).strip() + "\n")

    action_items = event.get("action_items") or []
    if action_items:
        lines.append("\n**行动项**\n")
        for item in action_items:
            owner = item.get("owner_id") or item.get("owner") or "未指定"
            due = item.get("due_date") or "未指定"
            lines.append(f"- {item.get('description', item)}（负责人：{owner}，截止：{due}）\n")

    signals = event.get("performance_signals")
    if signals:
        lines.append("\n**绩效信号**\n")
        for key, value in signals.items():
            lines.append(f"- {key}: {value}\n")
    return "".join(lines)


def safe_filename(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\s]+', "_", value.strip())
    return cleaned.strip("._") or "unknown"


def write_meeting_summary(run_dir: Path, event: dict[str, Any]) -> None:
    """Write weekly meeting summaries to dedicated JSONL and Markdown files."""
    append_jsonl(run_dir / "meeting_summaries.jsonl", event)

    date = event.get("date", "unknown-date")
    week_label = event.get("week_id", date)
    lines = [f"\n## {week_label} - 项目周会总结\n"]
    if event.get("week_start") and event.get("week_end"):
        lines.append(f"**周期**：{event.get('week_start')} 至 {event.get('week_end')}\n")
    if event.get("participant_names"):
        lines.append(f"**参会成员**：{', '.join(event['participant_names'])}\n")
    if event.get("task_ids"):
        lines.append(f"**相关任务**：{', '.join(event['task_ids'])}\n")

    issues = event.get("issues") or []
    if issues:
        lines.append("\n**本周处理问题**\n")
        for issue in issues:
            issue_id = issue.get("issue_id", "")
            topic = issue.get("topic", "")
            issue_type = issue.get("type", "")
            lines.append(f"- {issue_id} [{issue_type}] {topic}\n")

    content = event.get("content", "").strip()
    if content:
        lines.append("\n**会议转录摘要**\n")
        lines.append(content + "\n")

    action_items = event.get("action_items") or []
    if action_items:
        lines.append("\n**行动项**\n")
        for item in action_items:
            owner = item.get("owner_id") or item.get("owner") or "未指定"
            due = item.get("due_date") or "未指定"
            lines.append(f"- {item.get('description', item)}（负责人：{owner}，截止：{due}）\n")

    unresolved = event.get("unresolved_issues") or []
    if unresolved:
        lines.append("\n**遗留到下一周会的问题**\n")
        for issue in unresolved:
            lines.append(f"- {issue.get('issue_id', '')}: {issue.get('topic', '')}\n")

    with (run_dir / "meeting_summaries.md").open("a", encoding="utf-8") as handle:
        handle.write("".join(lines))


def write_member_event_logs(
    run_dir: Path,
    event: dict[str, Any],
    members: list[dict[str, Any]],
) -> None:
    """Append an event to per-member Markdown logs."""
    member_ids = set(event.get("member_ids") or [])
    if event.get("member_id"):
        member_ids.add(event["member_id"])
    if not member_ids:
        return

    by_id = {member.get("member_id"): member for member in members}
    member_dir = run_dir / "member_logs"
    member_dir.mkdir(parents=True, exist_ok=True)
    date = event.get("date", "unknown-date")
    event_type = event.get("event_type", "event")

    for member_id in sorted(member_ids):
        member = by_id.get(member_id, {"member_id": member_id, "name": member_id})
        filename = f"{safe_filename(member_id)}_{safe_filename(str(member.get('name', member_id)))}.md"
        path = member_dir / filename
        with path.open("a", encoding="utf-8") as handle:
            handle.write(render_member_event_markdown(date, event_type, event, member_id))


def render_member_event_markdown(
    date: str,
    event_type: str,
    event: dict[str, Any],
    member_id: str,
) -> str:
    lines = [f"\n## {date} - {event_type}\n"]
    if event.get("task_ids"):
        lines.append(f"**相关任务**：{', '.join(event['task_ids'])}\n")

    if event_type in {"daily_meeting", "weekly_meeting"}:
        transcript = [
            turn for turn in event.get("transcript", []) if turn.get("member_id") == member_id
        ]
        if transcript:
            lines.append("\n**我的会议发言**\n")
            for turn in transcript:
                lines.append(f"- {turn.get('message', '')}\n")
        related_issues = [
            issue
            for issue in event.get("issues", [])
            if member_id in set(issue.get("participant_ids") or [])
        ]
        if related_issues:
            lines.append("\n**我相关的问题**\n")
            for issue in related_issues:
                lines.append(f"- {issue.get('issue_id', '')}: {issue.get('topic', '')}\n")
    else:
        content = event.get("content") or event.get("summary") or ""
        lines.append(str(content).strip() + "\n")

    action_items = [
        item
        for item in event.get("action_items", []) or []
        if item.get("owner_id") in (None, member_id) or item.get("owner") == member_id
    ]
    if action_items:
        lines.append("\n**相关行动项**\n")
        for item in action_items:
            due = item.get("due_date") or "未指定"
            lines.append(f"- {item.get('description', item)}（截止：{due}）\n")
    return "".join(lines)


def write_weekly_stats(run_dir: Path, stats: dict[str, Any]) -> None:
    write_json(run_dir / "weekly_stats.json", stats)

    lines = ["# 每周生成统计\n"]
    for week_id in sorted(stats):
        item = stats[week_id]
        lines.append(f"\n## {week_id}\n")
        lines.append(f"- 事件总数：{item.get('events_total', 0)}\n")
        if item.get("event_types"):
            lines.append("- 事件类型：")
            lines.append(", ".join(f"{key}={value}" for key, value in item["event_types"].items()))
            lines.append("\n")
        if item.get("llm_calls"):
            lines.append("- LLM 调用：")
            lines.append(", ".join(f"{key}={value}" for key, value in item["llm_calls"].items()))
            lines.append("\n")
        if item.get("meeting"):
            meeting = item["meeting"]
            lines.append(
                f"- 周会：问题 {meeting.get('issues', 0)} 个，"
                f"发言 {meeting.get('turns', 0)} 轮，"
                f"行动项 {meeting.get('action_items', 0)} 个，"
                f"遗留 {meeting.get('unresolved_issues', 0)} 个\n"
            )
    (run_dir / "weekly_stats.md").write_text("".join(lines), encoding="utf-8")


def write_structured_json_output(
    run_dir: Path,
    *,
    project_background: str,
    project_scope: dict[str, Any],
    run_config: dict[str, Any],
    members: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    workweeks: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> None:
    """Write evaluation-friendly JSON files grouped by project, members, and weeks."""
    write_json(
        run_dir / "project_context.json",
        {
            "project_background": build_project_background(project_background, run_config, tasks),
            "project_scope": project_scope,
            "department_background": build_department_background(members),
            "analysis_note": "评价时需结合岗位职责、任务难度、协作依赖和项目阶段，不只按完成量评价。",
        },
    )
    write_json(run_dir / "members.json", [normalize_member_for_output(member) for member in members])

    weeks_dir = run_dir / "weeks"
    weeks_dir.mkdir(parents=True, exist_ok=True)
    reports_by_week: dict[str, list[dict[str, Any]]] = {}
    meetings_by_week: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        week_id = event.get("week_id")
        if not week_id:
            continue
        if event.get("event_type") == "weekly_report":
            reports_by_week.setdefault(str(week_id), []).append(event)
        elif event.get("event_type") == "weekly_meeting":
            meetings_by_week.setdefault(str(week_id), []).append(event)

    for week in workweeks:
        week_id = str(week["week_id"])
        week_data = {
            "week_id": week_id,
            "start_date": week["start_date"],
            "end_date": week["end_date"],
            "reports": [
                {
                    "member_id": event.get("member_id", ""),
                    "member_name": event.get("member_name", ""),
                    "content": event.get("content", ""),
                }
                for event in reports_by_week.get(week_id, [])
            ],
            "meetings": [
                {
                    "title": "项目周会",
                    "participants": event.get("member_ids", []),
                    "speeches": [
                        {
                            "member_id": turn.get("member_id", ""),
                            "member_name": turn.get("name", ""),
                            "content": turn.get("message", ""),
                        }
                        for turn in event.get("transcript", [])
                    ],
                }
                for event in meetings_by_week.get(week_id, [])
            ],
        }
        write_json(weeks_dir / f"{safe_filename(week_id)}.json", week_data)


def build_project_background(
    project_background: str,
    run_config: dict[str, Any],
    tasks: list[dict[str, Any]],
) -> str:
    task_titles = [
        str(task.get("title") or task.get("name") or task.get("task_id"))
        for task in tasks
        if task.get("title") or task.get("name") or task.get("task_id")
    ]
    deliverables = "\n".join(f"- {title}" for title in task_titles)
    return (
        f"{project_background.strip()}\n\n"
        f"项目周期：{run_config.get('start_date', '')} 至 {run_config.get('end_date', '')}\n\n"
        f"主要交付物/任务：\n{deliverables}\n\n"
        "成功标准：核心任务按周期完成，关键风险被及时暴露并在周会中形成行动项，最终交付物满足项目背景中的范围和质量要求。"
    ).strip()


def build_department_background(members: list[dict[str, Any]]) -> str:
    role_lines = []
    for member in members:
        name = member.get("name") or member.get("member_id", "")
        role = member.get("role", "")
        habits = member.get("work_habits", "")
        role_lines.append(f"- {name}：{role}。{habits}".strip())
    return (
        "团队采用项目制协作，成员按岗位承担不同职责，评价时需要区分项目管理、策划、设计、开发、执行等岗位差异。"
        "\n\n成员与协作方式：\n"
        + "\n".join(role_lines)
    ).strip()


def normalize_member_for_output(member: dict[str, Any]) -> dict[str, Any]:
    responsibilities = member.get("responsibilities")
    if not responsibilities:
        responsibilities = member.get("work_habits") or f"负责{member.get('role', '相关岗位')}相关工作。"
    return {
        "member_id": member.get("member_id", ""),
        "name": member.get("name", ""),
        "role": member.get("role", ""),
        "responsibilities": responsibilities,
        "profile": {
            "experience": member.get("experience", ""),
            "skills": member.get("skills", []),
            "strengths": member.get("strengths", []),
            "weaknesses": member.get("weaknesses", []),
            "communication_style": member.get("communication_style", ""),
            "work_habits": member.get("work_habits", ""),
            "persona_notes": member.get("persona_notes", ""),
        },
    }


def write_html_report(
    run_dir: Path,
    *,
    project_background: str,
    project_scope: dict[str, Any],
    run_config: dict[str, Any],
    members: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    events: list[dict[str, Any]],
    weekly_stats: dict[str, Any],
    errors: list[dict[str, Any]],
) -> None:
    """Write a self-contained HTML report for the generated run."""
    events_by_day: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        events_by_day.setdefault(str(event.get("date", "unknown-date")), []).append(event)

    total_llm_calls = sum(
        int(count)
        for week_stats in weekly_stats.values()
        for count in (week_stats.get("llm_calls") or {}).values()
    )
    event_type_counts: dict[str, int] = {}
    for event in events:
        event_type = str(event.get("event_type", "event"))
        event_type_counts[event_type] = event_type_counts.get(event_type, 0) + 1

    body = [
        "<!doctype html>",
        '<html lang="zh-CN">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{escape(str(run_config.get('run_id', 'MockWork Report')))}</title>",
        "<style>",
        HTML_REPORT_CSS,
        "</style>",
        "</head>",
        "<body>",
        '<main class="page">',
        "<header>",
        "<h1>MockWork 生成报告</h1>",
        f"<p>{escape(str(run_config.get('start_date', '')))} 至 {escape(str(run_config.get('end_date', '')))} · {escape(str(run_config.get('run_id', '')))}</p>",
        "</header>",
        '<section class="metrics">',
        _metric_card("成员", len(members)),
        _metric_card("任务", len(tasks)),
        _metric_card("事件", len(events)),
        _metric_card("LLM 调用", total_llm_calls),
        _metric_card("错误", len(errors)),
        "</section>",
        '<section class="panel">',
        "<h2>项目背景</h2>",
        f"<p>{escape(project_background).replace(chr(10), '<br>')}</p>",
        "</section>",
        '<section class="panel">',
        "<h2>项目范围规划</h2>",
        _render_project_scope(project_scope),
        "</section>",
        '<section class="grid">',
        '<div class="panel">',
        "<h2>成员</h2>",
        _render_member_list(members),
        "</div>",
        '<div class="panel">',
        "<h2>事件分布</h2>",
        _render_key_value_table(event_type_counts),
        "</div>",
        "</section>",
        '<section class="panel">',
        "<h2>任务终态</h2>",
        _render_task_table(tasks),
        "</section>",
        '<section class="panel">',
        "<h2>每周统计</h2>",
        _render_weekly_stats_table(weekly_stats),
        "</section>",
        '<section class="panel">',
        "<h2>每周记录</h2>",
        _render_events_by_day(events_by_day),
        "</section>",
    ]
    if errors:
        body.extend(
            [
                '<section class="panel">',
                "<h2>错误</h2>",
                _render_error_list(errors),
                "</section>",
            ]
        )
    body.extend(["</main>", "</body>", "</html>"])
    (run_dir / "report.html").write_text("\n".join(body), encoding="utf-8")


HTML_REPORT_CSS = """
:root {
  color-scheme: light;
  --bg: #f6f7f9;
  --panel: #ffffff;
  --text: #1f2933;
  --muted: #657384;
  --line: #d8dee7;
  --accent: #2f6f7e;
  --accent-soft: #e7f2f4;
  --danger: #a23b3b;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
  line-height: 1.55;
}
.page { width: min(1180px, calc(100% - 32px)); margin: 0 auto; padding: 28px 0 48px; }
header { margin-bottom: 18px; }
h1 { margin: 0 0 8px; font-size: 30px; letter-spacing: 0; }
h2 { margin: 0 0 14px; font-size: 19px; letter-spacing: 0; }
h3 { margin: 0 0 8px; font-size: 16px; letter-spacing: 0; }
p { margin: 0 0 10px; }
header p, .muted { color: var(--muted); }
.metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin: 18px 0; }
.metric, .panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 16px;
}
.metric strong { display: block; font-size: 26px; margin-bottom: 4px; }
.grid { display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(280px, .9fr); gap: 14px; }
.panel { margin-bottom: 14px; overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { border-bottom: 1px solid var(--line); padding: 9px 8px; text-align: left; vertical-align: top; }
th { color: var(--muted); font-weight: 600; background: #fbfcfd; }
ul { margin: 0; padding-left: 20px; }
.day { border-top: 1px solid var(--line); padding-top: 16px; margin-top: 16px; }
.event {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px;
  margin: 10px 0;
  background: #fbfcfd;
}
.event-title { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 8px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 999px; background: var(--accent-soft); color: var(--accent); font-size: 12px; }
.danger { color: var(--danger); }
.transcript { margin-top: 8px; }
.transcript p { border-left: 3px solid var(--line); padding-left: 10px; margin: 8px 0; }
@media (max-width: 760px) {
  .page { width: min(100% - 20px, 1180px); padding-top: 18px; }
  .grid { grid-template-columns: 1fr; }
  h1 { font-size: 24px; }
}
""".strip()


def _metric_card(label: str, value: int) -> str:
    return f'<div class="metric"><strong>{value}</strong><span>{escape(label)}</span></div>'


def _render_member_list(members: list[dict[str, Any]]) -> str:
    if not members:
        return '<p class="muted">无成员</p>'
    items = []
    for member in members:
        skills = member.get("skills") or []
        skill_text = "、".join(str(skill) for skill in skills) if isinstance(skills, list) else str(skills)
        details = []
        if member.get("communication_style"):
            details.append(f"沟通风格：{member['communication_style']}")
        if member.get("work_habits"):
            details.append(f"工作习惯：{member['work_habits']}")
        if member.get("persona_notes"):
            details.append(f"画像备注：{member['persona_notes']}")
        items.append(
            "<li>"
            f"<strong>{escape(str(member.get('name', member.get('member_id', ''))))}</strong>"
            f" <span class=\"muted\">{escape(str(member.get('role', '')))}</span>"
            f"<br><span class=\"muted\">{escape(skill_text)}</span>"
            + (
                f"<br><span class=\"muted\">{escape('；'.join(details))}</span>"
                if details
                else ""
            )
            + "</li>"
        )
    return "<ul>" + "\n".join(items) + "</ul>"


def _render_project_scope(project_scope: dict[str, Any]) -> str:
    if not project_scope:
        return '<p class="muted">无项目范围规划记录</p>'
    rows = []
    preferred_keys = [
        "project_version",
        "scope_adjustment",
        "scope_adjustment_reason",
        "time_adequacy",
        "time_adequacy_reason",
        "ideal_workdays",
        "ideal_team_size",
        "recommended_team_size",
        "team_structure",
        "adjusted_brief",
        "key_risks",
        "key_assumptions",
    ]
    for key in preferred_keys:
        if key not in project_scope:
            continue
        value = project_scope[key]
        if isinstance(value, (list, dict)):
            rendered_value = dumps_json(value)
        else:
            rendered_value = str(value)
        rows.append(
            f"<tr><td>{escape(key)}</td><td>{escape(rendered_value).replace(chr(10), '<br>')}</td></tr>"
        )
    return "<table><tbody>" + "".join(rows) + "</tbody></table>"


def _render_key_value_table(values: dict[str, int]) -> str:
    if not values:
        return '<p class="muted">无数据</p>'
    rows = [
        f"<tr><td>{escape(str(key))}</td><td>{value}</td></tr>"
        for key, value in sorted(values.items())
    ]
    return "<table><thead><tr><th>类型</th><th>数量</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"


def _render_task_table(tasks: list[dict[str, Any]]) -> str:
    if not tasks:
        return '<p class="muted">无任务</p>'
    rows = []
    for task in tasks:
        rows.append(
            "<tr>"
            f"<td>{escape(str(task.get('task_id', '')))}</td>"
            f"<td>{escape(str(task.get('title', task.get('name', ''))))}</td>"
            f"<td>{escape(str(task.get('owner_id', task.get('assignee', ''))))}</td>"
            f"<td>{escape(str(task.get('status', '')))}</td>"
            f"<td>{escape(str(task.get('progress', '')))}</td>"
            f"<td>{escape(str(task.get('priority', '')))}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>ID</th><th>任务</th><th>负责人</th>"
        "<th>状态</th><th>进度</th><th>优先级</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _render_weekly_stats_table(weekly_stats: dict[str, Any]) -> str:
    if not weekly_stats:
        return '<p class="muted">无统计</p>'
    rows = []
    for week_id, stats in sorted(weekly_stats.items()):
        llm_calls = stats.get("llm_calls") or {}
        meeting = stats.get("meeting") or {}
        rows.append(
            "<tr>"
            f"<td>{escape(str(week_id))}</td>"
            f"<td>{escape(str(stats.get('events_total', 0)))}</td>"
            f"<td>{escape(', '.join(f'{key}={value}' for key, value in llm_calls.items()))}</td>"
            f"<td>问题 {meeting.get('issues', 0)} / 发言 {meeting.get('turns', 0)} / 行动项 {meeting.get('action_items', 0)} / 遗留 {meeting.get('unresolved_issues', 0)}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>周期</th><th>事件数</th><th>LLM 调用</th><th>周会</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _render_events_by_day(events_by_day: dict[str, list[dict[str, Any]]]) -> str:
    if not events_by_day:
        return '<p class="muted">无事件</p>'
    sections = []
    for day, events in sorted(events_by_day.items()):
        sections.append(f'<div class="day"><h3>{escape(day)}</h3>')
        for event in events:
            sections.append(_render_html_event(event))
        sections.append("</div>")
    return "\n".join(sections)


def _render_html_event(event: dict[str, Any]) -> str:
    event_type = str(event.get("event_type", "event"))
    title = EVENT_TITLE_BY_TYPE.get(event_type, event_type)
    member = event.get("member_name") or ""
    task_ids = ", ".join(str(task_id) for task_id in event.get("task_ids", []) or [])
    parts = [
        '<article class="event">',
        '<div class="event-title">',
        f'<span class="badge">{escape(title)}</span>',
    ]
    if member:
        parts.append(f"<strong>{escape(str(member))}</strong>")
    if task_ids:
        parts.append(f'<span class="muted">任务：{escape(task_ids)}</span>')
    parts.append("</div>")
    content = str(event.get("content") or "").strip()
    if content:
        parts.append(f"<p>{escape(content).replace(chr(10), '<br>')}</p>")
    if event_type in {"daily_meeting", "weekly_meeting"}:
        parts.append(_render_meeting_details(event))
    action_items = event.get("action_items") or []
    if action_items:
        parts.append("<h3>行动项</h3><ul>")
        for item in action_items:
            owner = item.get("owner_id") or item.get("owner") or "未指定"
            due = item.get("due_date") or "未指定"
            parts.append(
                f"<li>{escape(str(item.get('description', item)))}"
                f" <span class=\"muted\">负责人：{escape(str(owner))}，截止：{escape(str(due))}</span></li>"
            )
        parts.append("</ul>")
    parts.append("</article>")
    return "\n".join(parts)


def _render_meeting_details(event: dict[str, Any]) -> str:
    parts = []
    issues = event.get("issues") or []
    if issues:
        parts.append("<h3>会议问题</h3><ul>")
        for issue in issues:
            parts.append(
                f"<li>{escape(str(issue.get('issue_id', '')))} "
                f"[{escape(str(issue.get('type', '')))}] "
                f"{escape(str(issue.get('topic', '')))}</li>"
            )
        parts.append("</ul>")
    transcript = event.get("transcript") or []
    if transcript:
        parts.append('<div class="transcript"><h3>发言</h3>')
        for turn in transcript:
            parts.append(
                f"<p><strong>{escape(str(turn.get('name', turn.get('member_id', ''))))}</strong>："
                f"{escape(str(turn.get('message', '')))}</p>"
            )
        parts.append("</div>")
    unresolved = event.get("unresolved_issues") or []
    if unresolved:
        parts.append('<h3 class="danger">遗留问题</h3><ul>')
        for issue in unresolved:
            parts.append(
                f"<li>{escape(str(issue.get('issue_id', '')))}："
                f"{escape(str(issue.get('topic', '')))}</li>"
            )
        parts.append("</ul>")
    return "\n".join(parts)


def _render_error_list(errors: list[dict[str, Any]]) -> str:
    items = [
        f"<li><strong>{escape(str(error.get('step', '')))}</strong>: {escape(str(error.get('content', '')))}</li>"
        for error in errors
    ]
    return '<ul class="danger">' + "\n".join(items) + "</ul>"


EVENT_TITLE_BY_TYPE = {
    "daily_report": "日报",
    "weekly_report": "周报",
    "task_update": "任务推进",
    "daily_meeting": "项目日会",
    "weekly_meeting": "项目周会",
    "member_summary": "成员周期汇总",
    "run_error": "生成错误",
}


def save_members_to_markdown(members: list[dict[str, Any]], file_path: Path = MEMBERS_FILE) -> None:
    """Save members data to markdown format."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# 项目成员档案\n"]
    for member in members:
        lines.append(f"\n## {member.get('name', member.get('member_id', member.get('id', 'Unknown')))}\n")
        lines.append(f"**成员 ID**：{member.get('member_id', member.get('id', 'N/A'))}\n")
        if member.get('role'):
            lines.append(f"**职位**：{member.get('role', 'N/A')}\n")
        if member.get('skills'):
            skills = member.get('skills', [])
            if isinstance(skills, list):
                lines.append(f"**技能**：{', '.join(skills)}\n")
            else:
                lines.append(f"**技能**：{skills}\n")
        if member.get('description'):
            lines.append(f"**描述**：{member.get('description')}\n")
        if member.get('base_salary'):
            lines.append(f"**薪资**：{member.get('base_salary')}\n")
        # Store full JSON representation as a code block for reference
        lines.append("\n**原始数据**：\n")
        lines.append("```json\n")
        lines.append(dumps_json(member) + "\n")
        lines.append("```\n")
    file_path.write_text("".join(lines), encoding="utf-8")


def save_tasks_to_markdown(tasks: list[dict[str, Any]], file_path: Path = TASKS_FILE) -> None:
    """Save tasks data to markdown format."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# 项目任务池\n"]
    for task in tasks:
        lines.append(f"\n## {task.get('title', task.get('name', task.get('task_id', task.get('id', 'Unknown'))))}\n")
        lines.append(f"**任务 ID**：{task.get('task_id', task.get('id', 'N/A'))}\n")
        if task.get('description'):
            lines.append(f"**描述**：{task.get('description')}\n")
        if task.get('assignee'):
            lines.append(f"**分配人**：{task.get('assignee', 'N/A')}\n")
        if task.get('owner_id'):
            lines.append(f"**负责人 ID**：{task.get('owner_id', 'N/A')}\n")
        if task.get('priority'):
            lines.append(f"**优先级**：{task.get('priority', 'N/A')}\n")
        if task.get('status'):
            lines.append(f"**状态**：{task.get('status', 'N/A')}\n")
        if task.get('estimated_effort'):
            lines.append(f"**预计工作量**：{task.get('estimated_effort')}\n")
        # Store full JSON representation as a code block for reference
        lines.append("\n**原始数据**：\n")
        lines.append("```json\n")
        lines.append(dumps_json(task) + "\n")
        lines.append("```\n")
    file_path.write_text("".join(lines), encoding="utf-8")


def log_llm_interaction(
    run_dir: Path | None = None,
    step: str = "",
    source: str = "",
    system: str = "",
    prompt: str = "",
    response: str = "",
    error: str | None = None,
) -> None:
    """Log LLM interaction to jsonl file."""
    log_file = (run_dir / "llm_interactions.jsonl") if run_dir else INIT_LLM_LOG_FILE
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "step": step,
        "source": source,
        "system": system,
        "prompt": prompt,
        "response": response,
        "error": error,
    }
    append_jsonl(log_file, log_entry)
