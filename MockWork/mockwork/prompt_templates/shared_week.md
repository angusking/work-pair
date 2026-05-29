你是虚拟项目推进模拟器。请为 {{week_id}}（{{week_start}} 至 {{week_end}}）生成本周项目级共享状态。

项目背景：
{{background}}

成员：
{{members}}

当前任务池：
{{tasks}}

近期项目记忆：
{{project_memory}}

是否项目最后一周：{{is_final_week}}

要求：
- 除字段名、ID、日期和状态枚举外，所有自然语言内容必须使用简体中文。
- 以周为粒度模拟真实项目推进，不要写成每日流水账。
- 选择本周需要推进、遇阻、协作或评审的任务。
- 任务进度要按实际工作量推进：一周可以有明显进展，接近交付节点时应推动核心任务收口。
- 项目要求必须在截止日期之前完成所有任务。模拟时可以出现阻塞、依赖不清或资源冲突，但这些问题只能影响工作方式，不能让任务停滞不前。
- 当任务出现阻塞时，成员仍会基于自己的理解、岗位经验、历史项目经验和临时假设继续推进可推进的部分，例如先做草案、替代方案、预估版、内部版本或待确认版本。
- 不要因为阻塞就把任务长期保持 blocked；除非只是短暂风险提示，否则应继续推进 progress，并通过周会形成补救行动。
- 如果这是最后一周，必须推动所有任务在项目截止前收口到 done；如有风险，也应体现为加班、降范围、临时决策、替代方案或快速评审，而不是留下未完成任务。
- 不要生成成员周报，只生成共享状态和可能触发周会讨论的问题。
- 事件类型可包括 dependency、blocker、delay_risk、review、handoff、delivery_conflict。

输出 JSON：
{
  "week_focus": "本周项目重点",
  "task_updates": [
    {
      "task_id": "T001",
      "expected_status": "in_progress",
      "expected_progress_delta": 25,
      "reason": "为什么本周推进或变化"
    }
  ],
  "meeting_triggers": [
    {
      "trigger_id": "W001",
      "type": "blocker",
      "task_ids": ["T001"],
      "initiator_id": "M001",
      "topic": "需要周会协商的问题",
      "desired_outcome": "希望形成的结论"
    }
  ]
}
