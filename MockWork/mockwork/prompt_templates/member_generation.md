基于以下项目背景生成 {{member_count}} 个虚拟项目成员。项目类型不要写死，要贴合背景。

项目背景：
{{background}}

可选组织结构：
{{org_structure}}

要求：
- 除字段名、ID、日期和状态枚举外，所有自然语言内容必须使用简体中文。
- 每个成员要有鲜明但真实的工作画像，例如细心但慢、有创新但容易失控、推进强但沟通粗糙。
- 不要直接给出绩效高低标签，要通过能力、短板、习惯和沟通风格体现差异。
- member_id 使用 M001、M002 递增。

输出 JSON：
{
  "members": [
    {
      "member_id": "M001",
      "name": "中文姓名",
      "role": "角色",
      "skills": ["技能"],
      "experience": "经验描述",
      "communication_style": "沟通风格",
      "strengths": ["优势"],
      "weaknesses": ["短板"],
      "work_habits": "工作习惯",
      "persona_notes": "能影响周报和沟通表现的人设备注"
    }
  ]
}
