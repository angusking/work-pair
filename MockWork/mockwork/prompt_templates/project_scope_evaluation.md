请根据项目简要说明和可用时间，规划一个在该时间范围内可完成的项目。

原始项目说明：
{{brief}}

项目周期：{{duration_days}} 日历天，预计 {{workdays_count}} 个工作日

要求：
0. 除字段名、ID、日期和状态枚举外，所有自然语言内容必须使用简体中文。

1. **评估原始需求的复杂度**（低/中/高），需要的理想时间和人力。

2. **如果时间充足**（理想时间的 1.2 倍以上）：
   - 保持原始项目范围
   - 详细规划主要阶段、交付物、团队分工
   - 标记为完整项目

3. **如果时间紧张**（理想时间的 0.5-1.2 倍）：
   - 核心功能/模块维持不变
   - 删除非必需功能、优化方案、完美化等
   - 交付物从产品改为演示版、从完整版改为核心版
   - 标记为精简版项目

4. **如果时间严重不足**（理想时间的 0.5 倍以下）：
   - 只保留核心需求中的核心
   - 变成简单的 Demo 或 PoC（概念证明）
   - 清晰说明演示的范围和限制
   - 标记为 Demo 版本

5. **列出关键风险和假设**。

输出 JSON（必须包含调整后的范围）：
{
  "original_complexity": "low|medium|high",
  "complexity_reason": "原始需求的复杂度评估",
  "ideal_workdays": 20,
  "ideal_team_size": 3,
  "time_adequacy": "insufficient|tight|moderate|comfortable",
  "time_adequacy_reason": "时间充足性分析和调整建议",
  "scope_adjustment": "full|simplified|demo",
  "scope_adjustment_reason": "为什么做这样的调整",
  "recommended_team_size": 3,
  "team_size_reason": "根据调整后的范围推荐的团队规模",
  "team_structure": "推荐的团队分工说明",
  "project_version": "完整版/精简版/Demo",
  "adjusted_brief": "调整后的项目范围详细说明，包括：\n- 保留的功能/模块\n- 删除或延期的部分（如果有）\n- 交付物定义\n- 关键里程碑",
  "key_phases": [
    {
      "phase_name": "阶段名",
      "description": "阶段说明",
      "workdays_estimate": 5,
      "deliverables": ["交付物1", "交付物2"]
    }
  ],
  "key_risks": [
    "风险1及其缓解方案"
  ],
  "key_assumptions": [
    "假设1：关键约束或前提"
  ],
  "proceed_recommendation": true
}
