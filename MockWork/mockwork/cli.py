from __future__ import annotations

from datetime import date
from typing import Any

from .calendar import parse_date, workdays_between
from .graph import WorkDataGenerator
from .initializer import initialize_project, load_project_assets
from .io import INIT_DIR, PROJECT_SCOPE_FILE, create_run_dir, ensure_directories, has_initialized_project, write_json
from .llm import OpenAICompatibleLLM
from .prompts import project_scope_evaluation_prompt, system_prompt


def main() -> None:
    ensure_directories()
    print("MockWork - 多 Agent 虚拟工作数据生成器")
    print("=" * 40)

    llm = OpenAICompatibleLLM.from_env()
    background, members, tasks, selected_dates, project_scope = choose_or_initialize(llm)
    start_date, end_date = selected_dates or ask_date_range()
    run_dir = create_run_dir()

    print(f"\n开始生成：{start_date.isoformat()} 到 {end_date.isoformat()}")
    print(f"输出目录：{run_dir}")
    generator = WorkDataGenerator(llm)
    final_state = generator.run(
        project_background=background,
        members=members,
        tasks=tasks,
        project_scope=project_scope,
        start_date=start_date,
        end_date=end_date,
        run_dir=run_dir,
    )
    print("\n生成完成")
    print(f"事件数量：{len(final_state.get('events', []))}")
    print(f"错误数量：{len(final_state.get('errors', []))}")
    print(f"JSONL：{run_dir / 'events.jsonl'}")
    print(f"Markdown：{run_dir / 'work_records.md'}")
    print(f"HTML：{run_dir / 'report.html'}")
    print(f"LLM日志：{run_dir / 'llm_interactions.jsonl'}")


def choose_or_initialize(
    llm: OpenAICompatibleLLM,
) -> tuple[
    str,
    list[dict[str, Any]],
    list[dict[str, Any]],
    tuple[date, date] | None,
    dict[str, Any],
]:
    if has_initialized_project():
        choice = input("检测到已有 init 内容。输入 1 复用，输入 2 重新输入项目 [1]: ").strip() or "1"
        if choice == "1":
            background, members, tasks, project_scope = load_project_assets()
            return background, members, tasks, None, project_scope

    # 新的流程：先输入简要说明和时间，进行范围规划
    print("\n========== 项目初始化 ==========")
    brief = ask_project_brief()
    start_date, end_date = ask_date_range()
    
    # 计算工作日数
    workdays = workdays_between(start_date, end_date)
    duration_days = (end_date - start_date).days + 1
    
    print(f"\n项目周期：{start_date} 到 {end_date}（{duration_days} 天，{len(workdays)} 个工作日）")
    print("\n正在规划项目范围...")
    
    # 获取项目范围规划（包含调整）
    planning = llm.json(
        system_prompt("project_scope"),
        project_scope_evaluation_prompt(brief, duration_days, len(workdays))
    )
    write_json(PROJECT_SCOPE_FILE, planning)
    
    # 显示评估和调整结果
    print("\n========== 项目范围规划 ==========")
    print(f"原始需求复杂度：{planning.get('original_complexity', 'N/A')} - {planning.get('complexity_reason', '')}")
    print(f"理想工期：{planning.get('ideal_workdays', 'N/A')} 工作日，{planning.get('ideal_team_size', 'N/A')} 人团队")
    
    scope_version = planning.get('project_version', '未知版本')
    scope_adjustment = planning.get('scope_adjustment', 'unknown')
    print(f"\n📋 项目版本：{scope_version}")
    print(f"   调整方式：{scope_adjustment}")
    print(f"   原因：{planning.get('scope_adjustment_reason', '')}")
    
    print(f"\n⏱️  时间充足性：{planning.get('time_adequacy', 'N/A')}")
    print(f"   分析：{planning.get('time_adequacy_reason', '')}")
    
    if planning.get('key_risks'):
        print("\n⚠️  关键风险：")
        for risk in planning.get('key_risks', []):
            print(f"   • {risk}")
    
    if planning.get('key_assumptions'):
        print("\n📌 关键假设：")
        for assumption in planning.get('key_assumptions', []):
            print(f"   • {assumption}")
    
    print(f"\n========== 调整后的项目范围 ==========")
    print(planning.get('adjusted_brief', brief))
    
    if planning.get('key_phases'):
        print(f"\n主要阶段：")
        for phase in planning.get('key_phases', []):
            workdays_est = phase.get('workdays_estimate', '?')
            print(f"  • {phase.get('phase_name', '未命名')} ({workdays_est} 工作日)")
            print(f"    {phase.get('description', '')}")
            if phase.get('deliverables'):
                for deliverable in phase.get('deliverables', []):
                    print(f"    ✓ {deliverable}")
    
    # 询问用户是否继续
    if not planning.get('proceed_recommendation', True):
        print("\n⚠️ 评估建议重新调整项目范围或时间。")
        proceed = input("是否继续？(y/n): ").strip().lower()
        if proceed != 'y':
            raise SystemExit("用户取消项目初始化。")
    else:
        print("\n✅ 项目范围规划完成，建议继续。")
    
    # 使用调整后的范围作为项目背景
    background = planning.get('adjusted_brief', brief)
    
    # 获取团队信息
    recommended_size = planning.get('recommended_team_size', 3)
    member_count_raw = input(f"\n项目人数 [{recommended_size}]: ").strip()
    member_count = int(member_count_raw) if member_count_raw else recommended_size
    
    team_structure = planning.get('team_structure', '')
    org_structure = input(f"组织结构 [{team_structure}]（可留空）: ").strip() or team_structure
    
    print("\n正在生成成员档案和任务池...")
    background, members, tasks = initialize_project(
        llm=llm,
        background=background,
        member_count=member_count,
        org_structure=org_structure,
    )
    from .io import INIT_LLM_LOG_FILE
    print(f"\n✅ 项目初始化完成")
    print(f"成员档案：{INIT_DIR / 'members.md'}")
    print(f"任务池：{INIT_DIR / 'tasks.md'}")
    print(f"LLM日志：{INIT_LLM_LOG_FILE}")
    return background, members, tasks, (start_date, end_date), planning


def ask_project_brief() -> str:
    """获取项目简要说明"""
    print("\n请输入项目简要说明（一行或多行，单独一行 END 结束）：")
    lines: list[str] = []
    while True:
        line = input()
        if line.strip().upper() == "END":
            break
        lines.append(line)
    brief = "\n".join(lines).strip()
    if not brief:
        raise SystemExit("项目说明不能为空。")
    return brief


def ask_date_range() -> tuple[date, date]:
    start = parse_date(input("开始日期 YYYY-MM-DD：").strip())
    end = parse_date(input("结束日期 YYYY-MM-DD：").strip())
    if end < start:
        raise SystemExit("结束日期不能早于开始日期。")
    return start, end
