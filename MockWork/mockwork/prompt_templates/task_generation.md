基于项目背景和成员列表，生成一个初始项目任务池。

项目背景：
{{background}}

成员：
{{members}}

要求：
- 除字段名、ID、日期和状态枚举外，所有自然语言内容必须使用简体中文。
- 任务要覆盖项目主要阶段和交付物。
- 任务拆解必须能在用户设定的项目周期内闭环，避免拆出过多无法按期完成的任务。
- owner_id 必须来自成员列表。
- collaborators 可以为空或包含成员 ID。
- task_id 使用 T001、T002 递增。
- status 初始为 todo 或 in_progress，progress 为 0-30 的整数。

输出 JSON：
{
  "tasks": [
    {
      "task_id": "T001",
      "title": "任务标题",
      "description": "任务描述",
      "owner_id": "M001",
      "collaborators": ["M002"],
      "status": "in_progress",
      "progress": 10,
      "priority": "medium",
      "due_date": null,
      "dependencies": [],
      "notes": "补充说明"
    }
  ]
}
