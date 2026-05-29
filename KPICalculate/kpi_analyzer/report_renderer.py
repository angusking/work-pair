from __future__ import annotations

import html
from pathlib import Path

from .constants import MODE_LABELS, REVIEWER_BUSINESS, REVIEWER_HRBP
from .models import ComparisonResult, Dimension, LoadedInput, RankingRow, ScoreSummary
from .scoring import OVERALL_KEY


def _context_label(key: str) -> str:
    if key == OVERALL_KEY:
        return "综合"
    if key == REVIEWER_HRBP:
        return "HRBP"
    if key == REVIEWER_BUSINESS:
        return "业务主管"
    return key


def _ranking_table_md(rows: list[RankingRow]) -> str:
    lines = ["| 排名 | 成员 | 角色 | 分数 | 有效场次 |", "|---:|---|---|---:|---:|"]
    for row in rows:
        lines.append(
            f"| {row.rank} | {row.member.name} ({row.member.member_id}) | "
            f"{row.member.role} | {_format_score(row.score)} | {row.valid_matches} |"
        )
    return "\n".join(lines)


def _comparison_table_md(results: list[ComparisonResult]) -> str:
    lines = [
        "| 周次 | 评价视角 | A | B | 胜者 | A分 | B分 | LLM | 原因 | 异常 |",
        "|---|---|---|---|---|---:|---:|---|---|---|",
    ]
    for result in results:
        if result.winner == "A":
            winner = result.member_a.name
        elif result.winner == "B":
            winner = result.member_b.name
        elif result.winner == "TIE":
            winner = "平局"
        else:
            winner = "-"
        lines.append(
            f"| {result.week_id} | {_context_label(result.reviewer or OVERALL_KEY)} | "
            f"{result.member_a.name} | {result.member_b.name} | {winner} | "
            f"{_format_score(result.score_a)} | "
            f"{_format_score(result.score_b)} | "
            f"{'是' if result.called_llm else '否'} | {result.reason or ''} | {result.error or ''} |"
        )
    return "\n".join(lines)


def _format_score(value: object) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value)


def _members_table_md(data: LoadedInput) -> str:
    lines = [
        "| 成员ID | 姓名 | 角色 | 职责/工作习惯 | 经验 | 技能 | 优势 | 风险/短板 | 沟通风格 | 画像备注 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for member in data.members:
        lines.append(
            f"| {member.member_id} | {member.name} | {member.role} | "
            f"{_md_cell(member.responsibilities)} | {_md_cell(member.profile.experience)} | "
            f"{_md_cell('、'.join(member.profile.skills))} | {_md_cell('、'.join(member.profile.strengths))} | "
            f"{_md_cell('、'.join(member.profile.weaknesses))} | "
            f"{_md_cell(member.profile.communication_style)} | {_md_cell(member.profile.persona_notes)} |"
        )
    return "\n".join(lines)


def _project_scope_md(data: LoadedInput) -> str:
    scope = data.project_context.project_scope
    if not scope:
        return "未提供"

    lines: list[str] = []
    simple_keys = [
        ("project_version", "项目版本"),
        ("scope_adjustment", "范围调整"),
        ("scope_adjustment_reason", "范围调整原因"),
        ("complexity_reason", "复杂度说明"),
        ("time_adequacy", "时间充足度"),
        ("time_adequacy_reason", "时间说明"),
        ("team_structure", "建议团队结构"),
        ("team_size_reason", "团队规模说明"),
    ]
    for key, label in simple_keys:
        value = scope.get(key)
        if value not in (None, "", []):
            lines.append(f"- {label}：{value}")

    if scope.get("key_assumptions"):
        lines.append("")
        lines.append("#### 关键假设")
        lines.append("")
        for item in scope["key_assumptions"]:
            lines.append(f"- {item}")

    if scope.get("key_risks"):
        lines.append("")
        lines.append("#### 关键风险")
        lines.append("")
        for item in scope["key_risks"]:
            lines.append(f"- {item}")

    if scope.get("key_phases"):
        lines.append("")
        lines.append("#### 项目阶段")
        lines.append("")
        lines.append("| 阶段 | 说明 | 预估工作日 | 交付物 |")
        lines.append("|---|---|---:|---|")
        for phase in scope["key_phases"]:
            lines.append(
                f"| {_md_cell(str(phase.get('phase_name', '')))} | "
                f"{_md_cell(str(phase.get('description', '')))} | "
                f"{phase.get('workdays_estimate', '')} | "
                f"{_md_cell('、'.join(phase.get('deliverables') or []))} |"
            )
    return "\n".join(lines)


def _tasks_table_md(data: LoadedInput) -> str:
    if not data.tasks:
        return "未提供"
    member_by_id = {member.member_id: member.name for member in data.members}
    lines = [
        "| 任务ID | 标题 | 负责人 | 协作者 | 依赖 | 优先级 | 状态 | 进度 | 说明 |",
        "|---|---|---|---|---|---|---|---:|---|",
    ]
    for task in data.tasks:
        owner = f"{member_by_id.get(task.owner_id, task.owner_id)} ({task.owner_id})" if task.owner_id else ""
        collaborators = ", ".join(f"{member_by_id.get(mid, mid)} ({mid})" for mid in task.collaborators)
        dependencies = ", ".join(task.dependencies)
        progress = "" if task.progress is None else str(task.progress)
        lines.append(
            f"| {task.task_id} | {_md_cell(task.title)} | {_md_cell(owner)} | {_md_cell(collaborators)} | "
            f"{_md_cell(dependencies)} | {task.priority} | {task.status} | {progress} | {_md_cell(task.notes or task.description)} |"
        )
    return "\n".join(lines)


def _input_weeks_md(data: LoadedInput) -> str:
    lines: list[str] = []
    for week in data.weeks:
        lines.append(f"### {week.week_id}（{week.start_date} 至 {week.end_date}）")
        lines.append("")
        lines.append("#### 周报")
        lines.append("")
        for report in week.reports:
            lines.append(f"##### {report.member_name}（{report.member_id}）")
            lines.append("")
            lines.append(report.content.strip() or "无")
            lines.append("")
        lines.append("#### 会议记录")
        lines.append("")
        if not week.meetings:
            lines.append("无")
            lines.append("")
            continue
        for meeting in week.meetings:
            lines.append(f"##### {meeting.title or '未命名会议'}")
            lines.append("")
            if meeting.participants:
                lines.append(f"- 参与成员：{', '.join(meeting.participants)}")
                lines.append("")
            if not meeting.speeches:
                lines.append("无结构化发言")
                lines.append("")
                continue
            for speech in meeting.speeches:
                lines.append(f"**{speech.member_name}（{speech.member_id}）**")
                lines.append("")
                lines.append(speech.content.strip() or "无")
                lines.append("")
    return "\n".join(lines)


def _md_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


def render_markdown(
    output_dir: Path,
    run_id: str,
    mode: str,
    data: LoadedInput,
    dimensions: list[Dimension],
    results: list[ComparisonResult],
    summary: ScoreSummary,
) -> Path:
    lines: list[str] = []
    lines.append("# 绩效分析报告")
    lines.append("")
    lines.append("## 运行概要")
    lines.append("")
    lines.append(f"- Run ID：`{run_id}`")
    lines.append(f"- 分析模式：{MODE_LABELS.get(mode, mode)}")
    lines.append(f"- 成员数：{len(data.members)}")
    lines.append(f"- 周次数：{len(data.weeks)}")
    lines.append(f"- 比较结果数：{summary.comparison_count}")
    lines.append(f"- 异常数：{summary.error_count}")
    lines.append("")

    lines.append("## 输入信息")
    lines.append("")
    lines.append("### 项目背景")
    lines.append("")
    lines.append(data.project_context.project_background.strip() or "未提供")
    lines.append("")
    lines.append("### 结构化项目范围")
    lines.append("")
    lines.append(_project_scope_md(data))
    lines.append("")
    lines.append("### 部门/岗位背景")
    lines.append("")
    lines.append(data.project_context.department_background.strip() or "未提供")
    lines.append("")
    if data.project_context.analysis_note.strip():
        lines.append("### 分析说明")
        lines.append("")
        lines.append(data.project_context.analysis_note.strip())
        lines.append("")
    lines.append("### 成员信息")
    lines.append("")
    lines.append(_members_table_md(data))
    lines.append("")
    lines.append("### 任务清单与最终状态")
    lines.append("")
    lines.append(_tasks_table_md(data))
    lines.append("")
    lines.append("### 每周工作材料")
    lines.append("")
    lines.append(_input_weeks_md(data))
    lines.append("")

    if dimensions:
        lines.append("## 绩效维度")
        lines.append("")
        for index, dimension in enumerate(dimensions, start=1):
            suffix = f"：{dimension.description}" if dimension.description else ""
            lines.append(f"{index}. {dimension.name}{suffix}")
        lines.append("")

    lines.append("## 总排名")
    lines.append("")
    for key, rows in summary.total.items():
        lines.append(f"### {_context_label(key)}")
        lines.append("")
        lines.append(_ranking_table_md(rows))
        lines.append("")

    lines.append("## 每周排名")
    lines.append("")
    for week_id, contexts in summary.weekly.items():
        lines.append(f"### {week_id}")
        lines.append("")
        for key, rows in contexts.items():
            lines.append(f"#### {_context_label(key)}")
            lines.append("")
            lines.append(_ranking_table_md(rows))
            lines.append("")

    lines.append("## 两两比较明细")
    lines.append("")
    lines.append(_comparison_table_md(results))
    lines.append("")

    lines.append("## 日志文件")
    lines.append("")
    lines.append("- `logs/run.log`")
    lines.append("- `logs/llm_interactions.jsonl`")
    lines.append("- `logs/comparisons.jsonl`")
    lines.append("- `logs/errors.jsonl`")
    lines.append("- `artifacts/run_snapshot.json`")
    lines.append("")

    path = output_dir / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def render_html(output_dir: Path, markdown_path: Path) -> Path:
    markdown = markdown_path.read_text(encoding="utf-8")
    body = _markdown_to_simple_html(markdown)
    html_doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>绩效分析报告</title>
  <style>
    :root {{
      --bg: #f6f7f9;
      --panel: #ffffff;
      --panel-soft: #f9fafb;
      --text: #20242a;
      --muted: #667085;
      --line: #d9dee7;
      --line-soft: #edf0f4;
      --accent: #1f6feb;
      --accent-soft: #e8f1ff;
      --success-soft: #e9f7ef;
      --warning-soft: #fff5df;
      --shadow: 0 1px 2px rgba(16, 24, 40, 0.06), 0 8px 24px rgba(16, 24, 40, 0.06);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: "Microsoft YaHei", "PingFang SC", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.68;
      letter-spacing: 0;
    }}
    .page {{
      max-width: 1280px;
      margin: 0 auto;
      padding: 28px 28px 56px;
    }}
    .report-title {{
      background: var(--panel);
      border: 1px solid var(--line-soft);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 24px 28px;
      margin-bottom: 18px;
    }}
    h1 {{
      margin: 0;
      font-size: 30px;
      line-height: 1.25;
      font-weight: 750;
      color: #111827;
    }}
    h2 {{
      margin: 28px 0 14px;
      padding: 16px 20px;
      background: var(--panel);
      border: 1px solid var(--line-soft);
      border-left: 5px solid var(--accent);
      border-radius: 8px;
      box-shadow: var(--shadow);
      font-size: 22px;
      line-height: 1.3;
      color: #111827;
    }}
    h3 {{
      margin: 24px 0 10px;
      font-size: 18px;
      line-height: 1.35;
      color: #182230;
      padding-bottom: 7px;
      border-bottom: 1px solid var(--line);
    }}
    h4 {{
      margin: 18px 0 8px;
      font-size: 15px;
      line-height: 1.35;
      color: #344054;
    }}
    h5 {{
      margin: 14px 0 6px;
      font-size: 14px;
      color: #475467;
    }}
    p {{
      margin: 8px 0;
      color: var(--text);
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }}
    .content-block {{
      background: var(--panel);
      border: 1px solid var(--line-soft);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 18px 20px;
      margin: 12px 0 18px;
    }}
    .table-wrap {{
      overflow-x: auto;
      margin: 12px 0 22px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: var(--shadow);
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      min-width: 760px;
      font-size: 13px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line-soft);
      padding: 9px 10px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      position: sticky;
      top: 0;
      z-index: 1;
      background: #eef3f8;
      color: #344054;
      font-weight: 700;
      white-space: nowrap;
    }}
    tr:nth-child(even) td {{ background: #fbfcfe; }}
    tr:hover td {{ background: var(--accent-soft); }}
    code {{
      background: #eef2f6;
      color: #344054;
      padding: 2px 5px;
      border-radius: 4px;
      font-family: Consolas, "SFMono-Regular", monospace;
      font-size: 0.92em;
    }}
    .bullet {{
      margin: 6px 0;
      padding: 8px 10px;
      background: var(--panel-soft);
      border: 1px solid var(--line-soft);
      border-radius: 6px;
      color: #344054;
    }}
    .muted {{ color: var(--muted); }}
    @media (max-width: 760px) {{
      .page {{ padding: 16px 12px 40px; }}
      .report-title {{ padding: 18px; }}
      h1 {{ font-size: 24px; }}
      h2 {{ font-size: 19px; padding: 14px 16px; }}
      table {{ font-size: 12px; }}
      th, td {{ padding: 8px; }}
    }}
  </style>
</head>
<body>
  <main class="page">
{body}
  </main>
</body>
</html>
"""
    path = output_dir / "report.html"
    path.write_text(html_doc, encoding="utf-8")
    return path


def _markdown_to_simple_html(markdown: str) -> str:
    lines = markdown.splitlines()
    html_lines: list[str] = []
    table_lines: list[str] = []
    paragraph_lines: list[str] = []
    in_block = False

    def open_block() -> None:
        nonlocal in_block
        if not in_block:
            html_lines.append('<section class="content-block">')
            in_block = True

    def close_block() -> None:
        nonlocal in_block
        flush_paragraph()
        if in_block:
            html_lines.append("</section>")
            in_block = False

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if not paragraph_lines:
            return
        open_block()
        text = "\n".join(paragraph_lines).strip()
        html_lines.append(f"<p>{_inline_markdown(text)}</p>")
        paragraph_lines = []

    def flush_table() -> None:
        nonlocal table_lines
        if not table_lines:
            return
        close_block()
        header = [cell.strip() for cell in table_lines[0].strip("|").split("|")]
        rows = table_lines[2:] if len(table_lines) > 1 else []
        html_lines.append('<div class="table-wrap"><table>')
        html_lines.append("<thead><tr>" + "".join(f"<th>{html.escape(cell)}</th>" for cell in header) + "</tr></thead>")
        html_lines.append("<tbody>")
        for row in rows:
            cells = [cell.strip() for cell in row.strip("|").split("|")]
            html_lines.append("<tr>" + "".join(f"<td>{_inline_markdown(cell)}</td>" for cell in cells) + "</tr>")
        html_lines.append("</tbody></table></div>")
        table_lines = []

    for line in lines:
        if line.startswith("|"):
            flush_paragraph()
            table_lines.append(line)
            continue
        flush_table()
        if line.startswith("# "):
            close_block()
            html_lines.append(f'<header class="report-title"><h1>{html.escape(line[2:])}</h1></header>')
        elif line.startswith("## "):
            close_block()
            html_lines.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("### "):
            close_block()
            html_lines.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("#### "):
            close_block()
            html_lines.append(f"<h4>{html.escape(line[5:])}</h4>")
        elif line.startswith("##### "):
            close_block()
            html_lines.append(f"<h5>{html.escape(line[6:])}</h5>")
        elif line.startswith("- "):
            open_block()
            html_lines.append(f'<div class="bullet">{_inline_markdown(line[2:])}</div>')
        elif line.strip():
            paragraph_lines.append(line)
        else:
            flush_paragraph()
    flush_table()
    close_block()
    return "\n".join(html_lines)


def _inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    result = ""
    index = 0
    while index < len(escaped):
        start = escaped.find("`", index)
        if start == -1:
            result += escaped[index:]
            break
        end = escaped.find("`", start + 1)
        if end == -1:
            result += escaped[index:]
            break
        result += escaped[index:start]
        result += "<code>" + escaped[start + 1 : end] + "</code>"
        index = end + 1
    return result.replace("&lt;br&gt;", "<br>")
