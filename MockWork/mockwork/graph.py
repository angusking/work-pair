from __future__ import annotations

import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from typing import Any

from langgraph.graph import END, StateGraph

from .calendar import workdays_between, workweeks_between
from .io import (
    append_jsonl,
    log_llm_interaction,
    write_html_report,
    write_json,
    write_markdown_event,
    write_meeting_summary,
    write_member_event_logs,
    write_run_metadata,
    write_structured_json_output,
    write_weekly_stats,
)
from .json_utils import dumps_json
from .llm import LLMClient
from .models import GraphState, RunConfig
from .prompts import (
    member_summary_prompt,
    shared_week_prompt,
    system_prompt,
    weekly_meeting_turn_prompt,
    weekly_report_prompt,
)


class WorkDataGenerator:
    def __init__(
        self,
        llm: LLMClient,
        *,
        verbose: bool = True,
        max_workers: int | None = None,
    ) -> None:
        self.llm = llm
        self.verbose = verbose
        self.max_workers = self._resolve_max_workers(max_workers)
        self._state_lock = threading.RLock()

    def _log(self, message: str) -> None:
        if self.verbose:
            print(message, flush=True)

    def _resolve_max_workers(self, max_workers: int | None) -> int:
        if max_workers is None:
            raw = os.getenv("MOCKWORK_MAX_WORKERS", "4").strip()
            try:
                max_workers = int(raw)
            except ValueError:
                max_workers = 4
        return max(1, max_workers)

    def build_graph(self):
        graph = StateGraph(GraphState)
        graph.add_node("prepare_run", self.prepare_run)
        graph.add_node("generate_days", self.generate_days)
        graph.add_node("finalize_run", self.finalize_run)
        graph.set_entry_point("prepare_run")
        graph.add_edge("prepare_run", "generate_days")
        graph.add_edge("generate_days", "finalize_run")
        graph.add_edge("finalize_run", END)
        return graph.compile()

    def run(
        self,
        *,
        project_background: str,
        members: list[dict[str, Any]],
        tasks: list[dict[str, Any]],
        start_date: date,
        end_date: date,
        run_dir: Path,
        project_scope: dict[str, Any] | None = None,
        max_retries: int = 3,
        max_conversation_turns: int = 6,
    ) -> GraphState:
        # Set log directory for LLM
        if hasattr(self.llm, 'log_dir'):
            self.llm.log_dir = run_dir

        self._log("\n========== 生成任务启动 ==========")
        self._log(f"项目周期：{start_date.isoformat()} 到 {end_date.isoformat()}")
        self._log(f"团队人数：{len(members)}，初始任务数：{len(tasks)}")
        self._log(f"LLM 并发数：{self.max_workers}")
        
        run_config = RunConfig(
            run_id=run_dir.name,
            start_date=start_date,
            end_date=end_date,
            model_name=self.llm.model_name,
            max_retries=max_retries,
            max_conversation_turns=max_conversation_turns,
        )
        initial_state: GraphState = {
            "project_background": project_background,
            "project_scope": project_scope or {},
            "members": members,
            "tasks": tasks,
            "run_config": run_config.to_dict(),
            "run_dir": str(run_dir),
            "events": [],
            "errors": [],
            "latest_reports": {},
            "project_memory": [],
            "carryover_weekly_issues": [],
            "weekly_stats": {},
            "llm_call_stats": {},
        }
        return self.build_graph().invoke(initial_state)

    def prepare_run(self, state: GraphState) -> GraphState:
        self._log("\n[阶段] 准备运行环境")
        run_dir = Path(state["run_dir"])
        config = state["run_config"]
        start = date.fromisoformat(config["start_date"])
        end = date.fromisoformat(config["end_date"])
        workdays = workdays_between(start, end)
        workweeks = workweeks_between(start, end)

        state["workdays"] = [day.isoformat() for day in workdays]
        state["workweeks"] = workweeks
        self._log(
            f"已识别 {len(workdays)} 个工作日，"
            f"{len(workweeks)} 个工作周。输出目录：{run_dir}"
        )
        write_run_metadata(
            run_dir,
            {
                "run_config": config,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "members": state["members"],
                "initial_tasks": state["tasks"],
                "workdays": state["workdays"],
                "workweeks": state["workweeks"],
            },
        )
        return state

    def generate_days(self, state: GraphState) -> GraphState:
        workweeks = state.get("workweeks", [])
        self._log("\n[阶段] 开始逐周模拟")
        for index, week in enumerate(workweeks, start=1):
            is_final_week = index == len(workweeks)
            week_id = str(week["week_id"])
            self._log(
                f"\n========== 模拟周 {week_id}（{index}/{len(workweeks)}，"
                f"{week['start_date']} 至 {week['end_date']}）=========="
            )
            self._log(f"[{week_id}] 生成项目共享状态...")
            week_context = self._call_json(
                state,
                f"shared_week:{week_id}",
                shared_week_prompt(
                    state["project_background"],
                    week,
                    state["members"],
                    state["tasks"],
                    state.get("project_memory", []),
                    is_final_week,
                ),
                fallback={"week_focus": "", "task_updates": [], "meeting_triggers": []},
            )
            self._apply_shared_task_updates(state, week_context.get("task_updates", []))
            focus = str(week_context.get("week_focus") or "未返回")
            update_count = len(week_context.get("task_updates", []) or [])
            trigger_count = len(week_context.get("meeting_triggers", []) or [])
            self._log(f"[{week_id}] 本周重点：{focus}")
            self._log(f"[{week_id}] 项目级任务更新：{update_count} 条，初始周会触发：{trigger_count} 条")

            report_requests: list[dict[str, Any]] = []
            for index_member, member in enumerate(state["members"]):
                related_tasks = self._tasks_for_member(state["tasks"], member["member_id"])
                self._log(
                    f"[{week_id}] 生成周报：{member.get('name', member['member_id'])}"
                    f"（相关任务 {len(related_tasks)} 个）..."
                )
                report_requests.append(
                    {
                        "index": index_member,
                        "member": member,
                        "step": f"weekly_report:{member['member_id']}:{week_id}",
                        "prompt": weekly_report_prompt(
                            state["project_background"],
                            week,
                            member,
                            related_tasks,
                            week_context,
                            state.get("latest_reports", {}).get(member["member_id"]),
                            is_final_week,
                        ),
                        "fallback": None,
                    }
                )

            for item in self._run_json_requests(state, report_requests):
                member = item["member"]
                report = item["result"]
                if not report:
                    self._log(f"[{week_id}] 周报跳过：{member.get('name', member['member_id'])}")
                    continue
                self._record_weekly_report(state, week, member, report)
                self._apply_member_task_updates(state, report.get("task_updates", []))
                self._log(
                    f"[{week_id}] 周报完成：{member.get('name', member['member_id'])}，"
                    f"任务更新 {len(report.get('task_updates', []) or [])} 条，"
                    f"周会请求 {len(report.get('needs_meeting', []) or [])} 条"
                )
                for meeting_item in report.get("needs_meeting", []):
                    week_context.setdefault("meeting_triggers", []).append(
                        {
                            "trigger_id": f"R-{member['member_id']}-{week_id}",
                            "type": meeting_item.get("type", "member_request"),
                            "task_ids": meeting_item.get("task_ids", []),
                            "initiator_id": member["member_id"],
                            "topic": meeting_item.get("topic", ""),
                            "desired_outcome": "形成明确行动项",
                        }
                    )

            meeting_issues = self._build_weekly_meeting_issues(
                state,
                week_id,
                week_context.get("meeting_triggers", []) or [],
            )
            if meeting_issues:
                self._run_weekly_meeting(state, week, meeting_issues, is_final_week)
            else:
                self._log(f"[{week_id}] 本周无协商问题，不召开周会。")

            self._log(f"[{week_id}] 本周模拟完成，累计事件 {len(state.get('events', []))} 条")

        return state

    def finalize_run(self, state: GraphState) -> GraphState:
        self._log("\n[阶段] 生成成员周期总结")
        summary_requests: list[dict[str, Any]] = []
        for index_member, member in enumerate(state["members"]):
            self._log(f"生成周期总结：{member.get('name', member['member_id'])}...")
            member_events = [
                event
                for event in state.get("events", [])
                if member["member_id"] in event.get("member_ids", [])
                or event.get("member_id") == member["member_id"]
            ]
            summary_requests.append(
                {
                    "index": index_member,
                    "member": member,
                    "step": f"member_summary:{member['member_id']}",
                    "prompt": member_summary_prompt(state["project_background"], member, member_events),
                    "fallback": None,
                }
            )

        for item in self._run_json_requests(state, summary_requests):
            member = item["member"]
            summary = item["result"]
            if not summary:
                self._log(f"周期总结跳过：{member.get('name', member['member_id'])}")
                continue
            event = {
                "run_id": state["run_config"]["run_id"],
                "date": state["run_config"]["end_date"],
                "event_type": "member_summary",
                "member_id": member["member_id"],
                "member_ids": [member["member_id"]],
                "member_name": member["name"],
                "content": summary.get("content", ""),
                "performance_signals": summary.get("performance_signals", {}),
            }
            self._write_event(state, event)
            self._log(f"周期总结完成：{member.get('name', member['member_id'])}")

        write_json(Path(state["run_dir"]) / "final_tasks.json", state["tasks"])
        write_json(Path(state["run_dir"]) / "errors.json", state.get("errors", []))
        write_structured_json_output(
            Path(state["run_dir"]),
            project_background=state["project_background"],
            project_scope=state.get("project_scope", {}),
            run_config=state["run_config"],
            members=state["members"],
            tasks=state["tasks"],
            workweeks=state.get("workweeks", []),
            events=state.get("events", []),
        )
        write_weekly_stats(Path(state["run_dir"]), state.get("weekly_stats", {}))
        write_html_report(
            Path(state["run_dir"]),
            project_background=state["project_background"],
            project_scope=state.get("project_scope", {}),
            run_config=state["run_config"],
            members=state["members"],
            tasks=state["tasks"],
            events=state.get("events", []),
            weekly_stats=state.get("weekly_stats", {}),
            errors=state.get("errors", []),
        )
        self._log(
            f"\n[完成] 生成结束：事件 {len(state.get('events', []))} 条，"
            f"错误 {len(state.get('errors', []))} 条"
        )
        return state

    def _build_weekly_meeting_issues(
        self,
        state: GraphState,
        week_id: str,
        triggers: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        raw_issues = list(state.get("carryover_weekly_issues", [])) + list(triggers)
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, tuple[str, ...], str]] = set()

        for raw in raw_issues:
            task_ids = [str(task_id) for task_id in raw.get("task_ids", []) if task_id]
            topic = str(raw.get("topic", "")).strip()
            issue_type = str(raw.get("type", "coordination")).strip() or "coordination"
            key = (issue_type, tuple(sorted(task_ids)), topic.replace(" ", ""))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(
                {
                    "issue_id": f"{week_id}-I{len(deduped) + 1:03d}",
                    "original_issue_id": raw.get("issue_id") or raw.get("trigger_id"),
                    "type": issue_type,
                    "task_ids": task_ids,
                    "initiator_id": raw.get("initiator_id"),
                    "topic": topic,
                    "desired_outcome": raw.get("desired_outcome", "形成明确行动项"),
                    "source": "carryover" if raw in state.get("carryover_weekly_issues", []) else "current_week",
                }
            )

        for issue in deduped:
            issue["participant_ids"] = self._issue_participant_ids(state, issue)

        carryover_count = sum(1 for issue in deduped if issue.get("source") == "carryover")
        self._log(
            f"[{week_id}] 周会问题评估：本周新增 {len(triggers)} 个，"
            f"遗留 {carryover_count} 个，合并后 {len(deduped)} 个"
        )
        return deduped

    def _run_weekly_meeting(
        self,
        state: GraphState,
        week: dict[str, Any],
        issues: list[dict[str, Any]],
        is_final_week: bool,
    ) -> None:
        week_id = str(week["week_id"])
        transcript: list[dict[str, Any]] = []
        action_items: list[dict[str, Any]] = []
        risk_notes: list[str] = []
        resolved_issue_ids: set[str] = set()
        explicitly_unresolved_issue_ids: set[str] = set()
        participants = self._weekly_meeting_participants(state, issues)
        if not participants:
            self._log(f"[{week_id}] 周会无相关参与人，跳过。")
            return

        max_turns = int(state["run_config"].get("max_conversation_turns", 6))
        issue_ids = {issue["issue_id"] for issue in issues}
        task_ids = sorted({task_id for issue in issues for task_id in issue.get("task_ids", [])})
        related_tasks = self._tasks_by_ids(state["tasks"], task_ids)
        participant_names = [member.get("name", member["member_id"]) for member in participants]
        self._log(
            f"[{week_id}] 召开项目周会：问题 {len(issues)} 个，"
            f"参会 {len(participants)} 人（{', '.join(participant_names)}）"
        )

        for turn in range(1, max_turns + 1):
            speaker = participants[(turn - 1) % len(participants)]
            speaker_issues = self._issues_for_member(issues, speaker["member_id"])
            self._log(
                f"[{week_id}] 周会第 {turn}/{max_turns} 轮："
                f"{speaker.get('name', speaker['member_id'])} 发言中..."
            )
            result = self._call_json(
                state,
                f"weekly_meeting:{week_id}:{turn}",
                weekly_meeting_turn_prompt(
                    state["project_background"],
                    week,
                    speaker,
                    issues,
                    speaker_issues,
                    related_tasks,
                    transcript,
                    turn,
                    max_turns,
                    is_final_week,
                ),
                fallback=None,
            )
            if not result:
                self._log(f"[{week_id}] 周会第 {turn} 轮未生成有效发言")
                continue

            message = self._extract_meeting_message(result)
            transcript.append(
                {
                    "member_id": speaker["member_id"],
                    "name": speaker["name"],
                    "issue_ids": [issue["issue_id"] for issue in speaker_issues],
                    "message": message,
                }
            )
            self._log(f"[{week_id}] {speaker.get('name', speaker['member_id'])}：{message}")
            action_items.extend(result.get("action_items", []) or [])
            risk_notes.extend(result.get("risk_notes", []) or [])
            resolved_issue_ids.update(
                issue_id
                for issue_id in result.get("resolved_issue_ids", []) or []
                if issue_id in issue_ids
            )
            explicitly_unresolved_issue_ids.update(
                issue_id
                for issue_id in result.get("unresolved_issue_ids", []) or []
                if issue_id in issue_ids
            )
            if result.get("should_stop") and action_items:
                self._log(f"[{week_id}] 周会已形成行动项，提前结束。")
                break

        if not transcript:
            self._log(f"[{week_id}] 周会未产生有效记录，全部问题遗留到下一周。")
            state["carryover_weekly_issues"] = issues
            return

        if resolved_issue_ids:
            unresolved_issue_ids = (issue_ids - resolved_issue_ids) | explicitly_unresolved_issue_ids
        elif action_items:
            unresolved_issue_ids = explicitly_unresolved_issue_ids
            resolved_issue_ids = issue_ids - unresolved_issue_ids
        else:
            unresolved_issue_ids = issue_ids

        unresolved_issues = [
            {**issue, "carryover_from": week_id}
            for issue in issues
            if issue["issue_id"] in unresolved_issue_ids
        ]
        state["carryover_weekly_issues"] = unresolved_issues

        content = "\n".join(f"{turn['name']}：{turn['message']}" for turn in transcript)
        event = {
            "run_id": state["run_config"]["run_id"],
            "date": str(week["end_date"]),
            "week_id": week_id,
            "week_start": week["start_date"],
            "week_end": week["end_date"],
            "event_type": "weekly_meeting",
            "member_ids": [member["member_id"] for member in participants],
            "participant_names": participant_names,
            "task_ids": task_ids,
            "issues": issues,
            "resolved_issue_ids": sorted(resolved_issue_ids),
            "unresolved_issues": unresolved_issues,
            "transcript": transcript,
            "content": content,
            "action_items": action_items,
            "risk_notes": risk_notes,
            "performance_signals": {
                "collaboration": 3,
                "initiative": 3 if action_items else 2,
                "risk": min(5, len(risk_notes) + len(unresolved_issues) + 1),
            },
        }
        self._write_event(state, event)
        write_meeting_summary(Path(state["run_dir"]), event)
        self._record_meeting_stats(state, week_id, event)
        self._log(
            f"[{week_id}] 周会记录已写入：发言 {len(transcript)} 条，"
            f"行动项 {len(action_items)} 条，遗留 {len(unresolved_issues)} 个"
        )
        if action_items:
            state.setdefault("project_memory", []).append(
                f"{week_id} 周会形成行动项："
                + "；".join(str(item.get("description", item)) for item in action_items)
            )

    def _extract_meeting_message(self, result: dict[str, Any]) -> str:
        if result.get("message") is not None:
            return str(result.get("message", "")).strip()
        speech = result.get("speech")
        if isinstance(speech, dict):
            for key in ("content", "message", "text"):
                if speech.get(key) is not None:
                    return str(speech.get(key, "")).strip()
        speeches = result.get("speeches")
        if isinstance(speeches, list) and speeches:
            first = speeches[0]
            if isinstance(first, dict):
                for key in ("content", "message", "text"):
                    if first.get(key) is not None:
                        return str(first.get(key, "")).strip()
            return str(first).strip()
        return ""

    def _issue_participant_ids(self, state: GraphState, issue: dict[str, Any]) -> list[str]:
        participants: set[str] = set()
        if issue.get("initiator_id"):
            participants.add(str(issue["initiator_id"]))
        for task in self._tasks_by_ids(state["tasks"], issue.get("task_ids", [])):
            if task.get("owner_id"):
                participants.add(str(task["owner_id"]))
            participants.update(str(member_id) for member_id in task.get("collaborators", []))
        project_manager_id = self._project_manager_id(state["members"])
        if project_manager_id:
            participants.add(project_manager_id)
        valid_ids = {member["member_id"] for member in state["members"]}
        return [member_id for member_id in participants if member_id in valid_ids]

    def _weekly_meeting_participants(
        self,
        state: GraphState,
        issues: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        participant_ids = {
            member_id
            for issue in issues
            for member_id in issue.get("participant_ids", [])
        }
        if not participant_ids:
            participant_ids = {member["member_id"] for member in state["members"]}
        manager_id = self._project_manager_id(state["members"])
        ordered = sorted(
            [member for member in state["members"] if member["member_id"] in participant_ids],
            key=lambda member: (
                member["member_id"] != manager_id,
                member["member_id"],
            ),
        )
        return ordered

    def _issues_for_member(
        self,
        issues: list[dict[str, Any]],
        member_id: str,
    ) -> list[dict[str, Any]]:
        return [issue for issue in issues if member_id in issue.get("participant_ids", [])]

    def _project_manager_id(self, members: list[dict[str, Any]]) -> str | None:
        for member in members:
            role = str(member.get("role", "")).lower()
            if "项目经理" in role or "manager" in role or role == "pm":
                return member.get("member_id")
        return members[0].get("member_id") if members else None

    def _record_meeting_stats(self, state: GraphState, day: str, event: dict[str, Any]) -> None:
        stats = state.setdefault("weekly_stats", {}).setdefault(day, {})
        stats["meeting"] = {
            "issues": len(event.get("issues", [])),
            "turns": len(event.get("transcript", [])),
            "action_items": len(event.get("action_items", [])),
            "unresolved_issues": len(event.get("unresolved_issues", [])),
        }

    def _run_json_requests(
        self,
        state: GraphState,
        requests: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not requests:
            return []
        if self.max_workers <= 1 or len(requests) == 1:
            return [
                {
                    **request,
                    "result": self._call_json(
                        state,
                        request["step"],
                        request["prompt"],
                        request.get("fallback"),
                    ),
                }
                for request in requests
            ]

        results: list[dict[str, Any]] = []
        worker_count = min(self.max_workers, len(requests))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(
                    self._call_json,
                    state,
                    request["step"],
                    request["prompt"],
                    request.get("fallback"),
                ): request
                for request in requests
            }
            for future in as_completed(futures):
                request = futures[future]
                results.append({**request, "result": future.result()})
        return sorted(results, key=lambda item: item.get("index", 0))

    def _record_weekly_report(
        self, state: GraphState, week: dict[str, Any], member: dict[str, Any], report: dict[str, Any]
    ) -> None:
        week_id = str(week["week_id"])
        task_ids = [item.get("task_id") for item in report.get("task_updates", []) if item.get("task_id")]
        event = {
            "run_id": state["run_config"]["run_id"],
            "date": str(week["end_date"]),
            "week_id": week_id,
            "week_start": week["start_date"],
            "week_end": week["end_date"],
            "event_type": "weekly_report",
            "member_id": member["member_id"],
            "member_ids": [member["member_id"]],
            "member_name": member["name"],
            "task_ids": task_ids,
            "content": report.get("content", ""),
            "task_updates": report.get("task_updates", []),
            "performance_signals": report.get("performance_signals", {}),
        }
        state.setdefault("latest_reports", {})[member["member_id"]] = event
        self._write_event(state, event)
        for update in report.get("task_updates", []):
            if not update.get("task_id"):
                continue
            task_event = {
                "run_id": state["run_config"]["run_id"],
                "date": str(week["end_date"]),
                "week_id": week_id,
                "week_start": week["start_date"],
                "week_end": week["end_date"],
                "event_type": "task_update",
                "member_id": member["member_id"],
                "member_ids": [member["member_id"]],
                "member_name": member["name"],
                "task_ids": [update["task_id"]],
                "content": update.get("note", ""),
                "task_update": update,
                "performance_signals": report.get("performance_signals", {}),
            }
            self._write_event(state, task_event)

    def _write_event(self, state: GraphState, event: dict[str, Any]) -> None:
        run_dir = Path(state["run_dir"])
        state.setdefault("events", []).append(event)
        append_jsonl(run_dir / "events.jsonl", event)
        write_markdown_event(run_dir, event)
        write_member_event_logs(run_dir, event, state.get("members", []))
        self._record_event_stats(state, event)

    def _record_event_stats(self, state: GraphState, event: dict[str, Any]) -> None:
        period = event.get("week_id") or event.get("date")
        if not period:
            return
        with self._state_lock:
            stats = state.setdefault("weekly_stats", {}).setdefault(str(period), {})
            stats["events_total"] = int(stats.get("events_total", 0)) + 1
            event_types = stats.setdefault("event_types", {})
            event_type = event.get("event_type", "event")
            event_types[event_type] = int(event_types.get(event_type, 0)) + 1

    def _record_llm_call_stats(self, state: GraphState, step: str) -> None:
        period = self._period_from_step(step) or state.get("run_config", {}).get("end_date")
        if not period:
            return
        with self._state_lock:
            stats = state.setdefault("weekly_stats", {}).setdefault(str(period), {})
            llm_calls = stats.setdefault("llm_calls", {})
            prefix = step.split(":", 1)[0]
            llm_calls[prefix] = int(llm_calls.get(prefix, 0)) + 1

    def _period_from_step(self, step: str) -> str | None:
        for part in step.split(":"):
            if re.match(r"^\d{4}-W\d{2}$", part):
                return part
            try:
                date.fromisoformat(part)
                return part
            except ValueError:
                continue
        return None

    def _record_error(self, state: GraphState, step: str, error: Exception) -> None:
        self._log(f"[错误] {step}: {error}")
        event = {
            "run_id": state["run_config"]["run_id"],
            "date": datetime.now().date().isoformat(),
            "event_type": "run_error",
            "step": step,
            "content": str(error),
        }
        with self._state_lock:
            state.setdefault("errors", []).append(event)
        append_jsonl(Path(state["run_dir"]) / "errors.jsonl", event)
        write_markdown_event(Path(state["run_dir"]), event)
        self._record_event_stats(state, event)

    def _call_json(
        self,
        state: GraphState,
        step: str,
        prompt: str,
        fallback: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        system = system_prompt("generator")
        run_dir = Path(state["run_dir"])
        self._record_llm_call_stats(state, step)
        try:
            result = self.llm.json(system, prompt)
            if isinstance(result, dict):
                log_llm_interaction(
                    run_dir=run_dir,
                    step=step,
                    source="generator",
                    system=system,
                    prompt=prompt,
                    response=dumps_json(result),
                )
                return result
            raise ValueError("LLM JSON response must be an object")
        except Exception as exc:
            log_llm_interaction(
                run_dir=run_dir,
                step=step,
                source="generator",
                system=system,
                prompt=prompt,
                response="",
                error=str(exc),
            )
            self._record_error(state, step, exc)
            return fallback

    def _tasks_for_member(self, tasks: list[dict[str, Any]], member_id: str) -> list[dict[str, Any]]:
        return [
            task
            for task in tasks
            if task.get("owner_id") == member_id or member_id in task.get("collaborators", [])
        ]

    def _tasks_by_ids(self, tasks: list[dict[str, Any]], task_ids: list[str]) -> list[dict[str, Any]]:
        ids = set(task_ids)
        return [task for task in tasks if task.get("task_id") in ids]

    def _apply_shared_task_updates(self, state: GraphState, updates: list[dict[str, Any]]) -> None:
        for update in updates:
            task = self._find_task(state["tasks"], update.get("task_id"))
            if not task:
                continue
            if update.get("expected_status"):
                task["status"] = update["expected_status"]
            delta = int(update.get("expected_progress_delta") or 0)
            task["progress"] = max(0, min(100, int(task.get("progress", 0)) + delta))
            if task["progress"] >= 100:
                task["status"] = "done"

    def _apply_member_task_updates(self, state: GraphState, updates: list[dict[str, Any]]) -> None:
        for update in updates:
            task = self._find_task(state["tasks"], update.get("task_id"))
            if not task:
                continue
            if update.get("status"):
                task["status"] = update["status"]
            if update.get("progress") is not None:
                task["progress"] = max(0, min(100, int(update["progress"])))
            if update.get("note"):
                task["notes"] = update["note"]

    def _find_task(self, tasks: list[dict[str, Any]], task_id: str | None) -> dict[str, Any] | None:
        for task in tasks:
            if task.get("task_id") == task_id:
                return task
        return None

    def _same_iso_week(self, value: str | None, year: int, week: int) -> bool:
        if not value:
            return False
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return False
        iso = parsed.isocalendar()
        return iso.year == year and iso.week == week
