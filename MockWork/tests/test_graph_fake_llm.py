from datetime import date
import json

import pytest

pytest.importorskip("langgraph")

from mockwork.graph import WorkDataGenerator


class FakeLLM:
    model_name = "fake-model"

    def json(self, system: str, prompt: str):
        if "本周项目级共享状态" in prompt:
            return {
                "week_focus": "推进核心交付",
                "task_updates": [
                    {
                        "task_id": "T001",
                        "expected_status": "in_progress",
                        "expected_progress_delta": 10,
                        "reason": "进入执行阶段",
                    }
                ],
                "meeting_triggers": [
                    {
                        "trigger_id": "C001",
                        "type": "blocker",
                        "task_ids": ["T001"],
                        "initiator_id": "M001",
                        "topic": "接口依赖未确认",
                        "desired_outcome": "明确负责人和截止时间",
                    }
                ],
            }
        if "工作周报" in prompt:
            return {
                "content": "完成了相关工作，发现一个依赖问题，明天继续推进。",
                "task_updates": [
                    {
                        "task_id": "T001",
                        "status": "in_progress",
                        "progress": 30,
                        "note": "完成初步推进",
                    }
                ],
                "needs_meeting": [],
                "performance_signals": {
                    "completion": 3,
                    "collaboration": 3,
                    "initiative": 3,
                    "quality": 3,
                    "risk": 2,
                    "blocker": "接口依赖未确认",
                },
            }
        if "项目周会" in prompt:
            return {
                "message": "我会配合确认依赖，并在明天下班前同步结论。",
                "should_stop": True,
                "resolved_issue_ids": ["2026-W22-I001"],
                "unresolved_issue_ids": [],
                "action_items": [
                    {
                        "description": "确认接口依赖",
                        "owner_id": "M001",
                        "due_date": "2026-05-25",
                        "issue_ids": ["2026-W22-I001"],
                    }
                ],
                "risk_notes": [],
            }
        if "项目周会纪要" in prompt:
            return {
                "content": "本周完成核心推进，接口依赖需要继续关注。",
                "action_items": [],
                "performance_signals": {
                    "team_risk": 2,
                    "collaboration_quality": 3,
                    "delivery_confidence": 3,
                },
            }
        if "工作情况汇总" in prompt:
            return {
                "content": "周期内能够持续推进任务，并主动暴露依赖风险。",
                "performance_signals": {
                    "completion": 3,
                    "collaboration": 3,
                    "initiative": 3,
                    "quality": 3,
                    "risk": 2,
                },
            }
        raise AssertionError(prompt)

    def text(self, system: str, prompt: str) -> str:
        return ""


def test_graph_generates_events_and_files(tmp_path):
    members = [
        {
            "member_id": "M001",
            "name": "张晨",
            "role": "项目经理",
            "skills": ["计划"],
            "experience": "5年",
            "communication_style": "直接",
            "strengths": ["推进"],
            "weaknesses": ["急躁"],
            "work_habits": "每日同步",
        },
        {
            "member_id": "M002",
            "name": "李想",
            "role": "开发",
            "skills": ["实现"],
            "experience": "3年",
            "communication_style": "谨慎",
            "strengths": ["细致"],
            "weaknesses": ["偏慢"],
            "work_habits": "先验证再提交",
        },
    ]
    tasks = [
        {
            "task_id": "T001",
            "title": "核心交付",
            "description": "完成核心工作",
            "owner_id": "M001",
            "collaborators": ["M002"],
            "status": "todo",
            "progress": 0,
            "priority": "high",
            "due_date": None,
            "dependencies": [],
            "notes": "",
        }
    ]

    state = WorkDataGenerator(FakeLLM()).run(
        project_background="一个测试项目",
        members=members,
        tasks=tasks,
        start_date=date(2026, 5, 25),
        end_date=date(2026, 5, 25),
        run_dir=tmp_path,
    )

    assert any(event["event_type"] == "weekly_report" for event in state["events"])
    assert any(event["event_type"] == "weekly_meeting" for event in state["events"])
    assert (tmp_path / "events.jsonl").exists()
    assert (tmp_path / "work_records.md").exists()
    assert (tmp_path / "meeting_summaries.md").exists()
    assert (tmp_path / "member_logs" / "M001_张晨.md").exists()
    assert (tmp_path / "weekly_stats.json").exists()
    assert (tmp_path / "report.html").exists()
    assert (tmp_path / "project_context.json").exists()
    assert (tmp_path / "members.json").exists()
    assert (tmp_path / "weeks" / "2026-W22.json").exists()
    assert "MockWork 生成报告" in (tmp_path / "report.html").read_text(encoding="utf-8")
    project_context = json.loads((tmp_path / "project_context.json").read_text(encoding="utf-8"))
    assert set(project_context) == {
        "project_background",
        "project_scope",
        "department_background",
        "analysis_note",
    }
    members_json = json.loads((tmp_path / "members.json").read_text(encoding="utf-8"))
    assert members_json[0]["profile"]["skills"] == ["计划"]
    assert members_json[0]["profile"]["communication_style"] == "直接"
    week_json = json.loads((tmp_path / "weeks" / "2026-W22.json").read_text(encoding="utf-8"))
    assert week_json["week_id"] == "2026-W22"
    assert week_json["reports"][0]["member_id"] == "M001"
    assert week_json["meetings"][0]["title"] == "项目周会"
    assert "content" not in week_json["meetings"][0]
    assert week_json["meetings"][0]["speeches"][0] == {
        "member_id": "M001",
        "member_name": "张晨",
        "content": "我会配合确认依赖，并在明天下班前同步结论。",
    }
    llm_logs = [
        json.loads(line)
        for line in (tmp_path / "llm_interactions.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    steps = {entry["step"] for entry in llm_logs}
    assert "shared_week:2026-W22" in steps
    assert "weekly_report:M001:2026-W22" in steps
    assert "weekly_meeting:2026-W22:1" in steps
