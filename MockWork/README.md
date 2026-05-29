# MockWork

基于 LangGraph 的多 Agent 虚拟工作数据生成器。它会根据项目背景生成虚拟成员、任务池、成员周报、事件触发的项目周会和成员周期总结。

## 安装

```powershell
cd D:\python\kpiSkill\MockWork
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

然后编辑 `.env`：

```text
OPENAI_API_KEY=你的 key
OPENAI_BASE_URL=https://你的-openai-compatible-endpoint/v1
OPENAI_MODEL=你的模型名
MOCKWORK_MAX_WORKERS=4
```

## 运行

```powershell
python -m mockwork
```

## 提示词

所有当前运行流程会发送给 LLM 的 system prompt 和 user prompt 都放在：

```text
mockwork/prompt_templates/
```

修改这些模板文件后重新运行即可生效，不需要改 Python 代码。模板变量使用 `{{变量名}}` 形式。

启动后：

1. 如果 `init/` 已有项目背景、成员档案、任务池，可以选择复用。
2. 如果重新输入项目背景，输入多行背景后用单独一行 `END` 结束。
3. 输入项目人数、可选组织结构、起止日期。
4. 输出会写入 `runs/run_YYYYMMDD_HHMMSS/`。

## 输出

- `events.jsonl`：事件流，每行一个 JSON 事件。
- `work_records.md`：按日期组织的可读 Markdown。
- `report.html`：最终 HTML 报告，整合项目背景、统计、任务终态、周会和事件记录。
- `project_context.json`：评价模型使用的项目上下文，包含项目背景、部门背景和评价注意事项。
- `members.json`：评价模型使用的成员档案。
- `weeks/`：按周拆分的周报和周会记录，例如 `weeks/2025-W18.json`。
- `run_metadata.json`：本次生成的模型、日期、成员、初始任务等追踪信息。
- `final_tasks.json`：周期结束后的任务状态。
- `errors.jsonl` / `errors.json`：失败调用和跳过项。
- `llm_interactions.jsonl`：生成过程中的 LLM 调用日志，按步骤记录 prompt、response 和错误。
- `weekly_stats.json` / `weekly_stats.md`：按模拟周统计事件数量、LLM 调用和周会情况。
- `meeting_summaries.jsonl` / `meeting_summaries.md`：每周一次项目周会的独立总结记录。
- `member_logs/`：按成员拆分的个人工作记录。

事件类型包括：

- `weekly_report`
- `task_update`
- `weekly_meeting`
- `member_summary`
- `run_error`

## 说明

- 第一版固定生成中文内容。
- 周报按自然工作周生成。
- 多 Agent 协商由阻塞、依赖、延期、评审、交付冲突等事件触发；每周最多合并为一次项目周会，只邀请相关成员参与，按成员顺序轮转发言，最多 6 轮。
- 同一周的成员周报和周期末成员总结会并发调用 LLM，默认并发数为 4，可通过 `MOCKWORK_MAX_WORKERS` 调整。共享状态和周会逐轮发言仍按顺序生成。
