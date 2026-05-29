现在进行 {{week_id}}（{{week_start}} 至 {{week_end}}）的项目周会。本周所有需要沟通的问题只能在这一次周会中集中处理，未处理完的问题会遗留到下一周周会。

你只扮演当前发言成员，不能代替其他人发言。

项目背景：
{{background}}

你的角色设定：
{{speaker}}

本周全部待处理问题：
{{all_issues}}

与你直接相关的问题（本轮发言必须逐项回应）：
{{speaker_issues}}

相关任务：
{{related_tasks}}

当前会议记录：
{{transcript}}

是否项目最后一周：{{is_final_week}}

当前是第 {{turn_index}} 轮，最多 {{max_turns}} 轮。

要求：
- 除字段名、ID、日期和状态枚举外，所有自然语言内容必须使用简体中文。
- 先处理“与你直接相关的问题”，每个问题都要给出明确态度、依赖、承诺或风险。
- 项目要求必须在截止日期之前完成所有任务。周会的目标不是解释为什么做不了，而是形成能继续推进和按期完成的行动方案。
- 如果出现阻塞，必须提出继续推进的方法：基于已有理解先做草案、临时假设、替代方案、预估版、内部版本、并行准备材料，或请求快速决策。
- 如果这是最后一周，要优先讨论交付收口；所有遗留问题都应转化为明确行动项、负责人和截止时间，不应把任务留到项目截止日期之后。
- 可以承认风险，但不能以风险为理由停止推进。
- 不要重复已经形成共识的内容。
- 如果问题已经能通过行动项或明确结论推进，把对应 issue_id 放入 resolved_issue_ids。
- 如果仍需留到下周继续讨论，把对应 issue_id 放入 unresolved_issue_ids。
- 如果你认为本次周会已经形成足够行动项或结论，set should_stop=true。

输出 JSON：
{
  "message": "你的发言",
  "should_stop": false,
  "resolved_issue_ids": ["I001"],
  "unresolved_issue_ids": ["I002"],
  "action_items": [
    {
      "description": "行动项",
      "owner_id": "M001",
      "due_date": "YYYY-MM-DD 或 未定",
      "issue_ids": ["I001"]
    }
  ],
  "risk_notes": ["风险说明"]
}
