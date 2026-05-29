请基于周期内记录，生成成员 {{member_name}} 的工作情况汇总。

项目背景：
{{background}}

成员设定：
{{member}}

相关事件：
{{member_events}}

要求：
- 除字段名、ID、日期和状态枚举外，所有自然语言内容必须使用简体中文。

输出 JSON：
{
  "content": "成员周期工作情况总结，包括主要贡献、协作、风险、改进点",
  "performance_signals": {
    "completion": 3,
    "collaboration": 3,
    "initiative": 3,
    "quality": 3,
    "risk": 2
  }
}
