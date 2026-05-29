# 通用绩效分析 CLI 设计

## 代码结构

```text
KPICalculate/
  main.py
  kpi_analyzer/
    __init__.py
    constants.py
    models.py
    env_loader.py
    input_loader.py
    validator.py
    material_builder.py
    prompt_loader.py
    llm_client.py
    dimension_service.py
    pair_builder.py
    comparison_runner.py
    scoring.py
    report_renderer.py
    run_logger.py
    jsonl_logger.py
    errors.py
  prompts/
    dimension_generation.md
    dimension_auto_select_for_reviewers.md
    compare_direct_batch.md
    compare_by_dimensions_batch.md
    compare_as_hrbp_batch.md
    compare_as_business_lead_batch.md
    compare_by_dimensions_as_reviewer_batch.md
    result_normalization.md
  input/
    project_context.json
    members.json
    weeks/*.json
  output/
  .env
  PROJECT.md
  DESIGN.md
```

第一版只读取标准输入：

```text
input/project_context.json
input/members.json
input/weeks/*.json
input/final_tasks.json
```

其中 `final_tasks.json` 为可选输入，只用于报告展示和项目总览，不进入逐周比较 prompt，避免最终状态影响早期周次判断。

不再兼容旧结构：

```text
events.jsonl
meeting_summaries.jsonl
run_metadata.json
member_logs/
```

## 固定运行参数

固定值放在 `kpi_analyzer/constants.py`：

```text
INPUT_DIR = "input"
OUTPUT_DIR = "output"
CONCURRENCY = 3
MAX_RETRIES = 3
TIMEOUT_SECONDS = 120
TEMPERATURE = 0
MAX_PAIRS_PER_LLM_CALL = 10
```

`.env` 必须包含：

```env
LLM_BASE_URL=https://api.example.com/v1
LLM_API_KEY=your-api-key
LLM_MODEL=your-model-name
```

缺少任一变量时，程序终止。

## 主流程

```text
main.py
  1. 初始化 run_id 和输出目录
  2. 初始化运行日志和控制台进度输出
  3. 读取 .env
  4. 读取 input JSON
  5. 校验输入完整性
  6. 询问分析模式
  7. 根据输入完整性处理模式可用性
  8. 如选择模式 2，生成维度并让用户选择排序
  9. 如选择模式 4，自动生成 5 个岗位侧重维度
 10. 生成每周 pair
 11. 应用缺材料规则，拆出自动判定 pair 和 LLM pair
 12. 按周、评价官、批次并发调用 LLM
 13. 校验和解析 LLM 结果
 14. 计分和排序
 15. 输出 Markdown、HTML、JSONL 日志
 16. 打印运行完成摘要
```

## 模块职责

### `models.py`

定义核心数据结构。

建议使用 `dataclasses`，减少依赖。

主要模型：

```text
ProjectContext
Member
MemberProfile
WeekData
WeeklyReport
Meeting
Speech
Pair
ComparisonBatch
ComparisonResult
Dimension
RankingRow
RunSummary
```

### `env_loader.py`

职责：

- 读取 `.env`
- 校验 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`
- 不从命令行询问 API 配置
- 不提供 mock 模式

### `input_loader.py`

职责：

- 读取 `input/project_context.json`
- 读取 `input/members.json`
- 按文件名排序读取 `input/weeks/*.json`
- 转换为内部模型

周次排序规则：

```text
优先按 week_id 字符串排序
例如 2026-W18, 2026-W19
```

### `validator.py`

职责：

- 校验项目背景是否存在
- 校验部门/岗位背景是否存在
- 校验成员最低字段：`member_id`、`name`、`role`
- 校验周报成员 ID 是否合法
- 校验会议 `speeches` 中成员 ID 是否合法
- 校验每周结构是否有 `week_id`、`start_date`、`end_date`

模式限制：

- 缺项目背景：只能执行模式 1
- 缺成员职位信息：只能执行模式 1
- direct 可以在背景不完整时运行，但要记录警告

### `material_builder.py`

职责：

- 为每个成员构造某周个人材料
- 合并该成员周报
- 从 `meetings[].speeches[]` 提取该成员会议发言
- 构造本周会议全文，供 prompt 使用
- 判断成员是否缺材料

缺材料规则：

```text
无周报且无会议发言 -> 缺材料
有周报或有会议发言 -> 有材料
```

注意：

- `participants` 只作为会议信息展示
- `participants` 不用于判定个人材料

### `pair_builder.py`

职责：

- 每周对所有成员生成 pair
- pair_id 格式：

```text
{week_id}__{reviewer_or_mode}__{member_a_id}__{member_b_id}
```

示例：

```text
2026-W18__direct__M001__M002
2026-W18__hrbp__M001__M002
```

### `prompt_loader.py`

职责：

- 从 `prompts/` 读取提示词模板
- 用简单占位符替换渲染 prompt
- 不把 prompt 写死在 Python 代码里

占位符示例：

```text
{{project_context}}
{{department_context}}
{{analysis_note}}
{{members}}
{{week_id}}
{{week_range}}
{{weekly_meeting}}
{{pairs_json}}
{{dimensions}}
{{reviewer_role}}
```

### `dimension_service.py`

职责：

- 模式 2：调用大模型生成 5 到 10 个绩效维度
- 模式 2：展示维度并读取用户选择排序
- 模式 4：调用大模型自动选择 5 个岗位侧重维度
- 保存 `selected_dimensions.json`

模式 2 的选择校验：

- 至少 3 个维度
- 编号必须存在
- 不允许重复

模式 4：

- 用户不参与维度选择
- 模型必须返回 5 个维度
- 如果返回数量不是 5，记录异常并终止模式 4

### `llm_client.py`

职责：

- 使用标准库 HTTP 客户端调用 OpenAI 兼容接口
- 请求地址：`{LLM_BASE_URL}/chat/completions`
- 支持超时
- 支持最多 3 次重试
- temperature 固定为 0

请求体结构：

```json
{
  "model": "from env",
  "temperature": 0,
  "messages": [
    {
      "role": "user",
      "content": "rendered prompt"
    }
  ]
}
```

### `comparison_runner.py`

职责：

- 按周、评价官、批次构造比较任务
- 自动判定缺材料 pair
- 对 LLM pair 按 `MAX_PAIRS_PER_LLM_CALL = 10` 分批
- 用 `asyncio` 并发执行批次
- 校验模型返回
- 输出标准化 `ComparisonResult`

批次失败：

```text
整个批次重试，最多 3 次
仍失败 -> 批次内所有 pair 记异常，不计分
```

批次部分异常：

```text
有效 pair 正常计分
异常 pair 不补救
异常 pair 记录到 errors.jsonl
```

### `scoring.py`

职责：

- 读取所有 `ComparisonResult`
- 计算每周分数
- 计算总分
- 处理评价官分数
- 处理综合分数
- 同分并列

计分：

```text
胜 = 1
平 = 0.5
负 = 0
异常 = 不计分
```

### `report_renderer.py`

职责：

- 输出 `report.md`
- 输出静态自包含 `report.html`
- 不依赖外部 CSS/JS

报告内容：

- 运行概要
- 分析模式
- 项目背景
- 结构化项目范围
- 部门/岗位背景
- 成员信息
- 任务清单与最终状态
- 每周工作周报
- 每周会议发言
- 总排名
- 每周排名
- HRBP/业务主管排名，若有
- 综合排名，若有
- 用户选择维度，若有
- 自动岗位侧重维度，若有
- 两两比较明细
- 每场比较的简短原因
- 异常摘要
- 日志文件路径

### `jsonl_logger.py`

职责：

- 追加写 JSONL
- 保证中文不转义
- 每条日志一行
- 主要服务于机器可读日志

### `run_logger.py`

职责：

- 记录清晰的人类可读运行过程
- 同时输出到控制台和 `run.log`
- 用于让用户实时看到进展

## 日志设计

每次运行创建独立目录：

```text
output/
  latest_run.txt
  runs/
    run_YYYYMMDD_HHMMSS/
      logs/
        run.log
        comparisons.jsonl
        llm_interactions.jsonl
        errors.jsonl
      reports/
        report.md
        report.html
      artifacts/
        selected_dimensions.json
        run_snapshot.json
```

### `run.log`

人类可读运行日志，记录清晰的程序运行过程。

示例：

```text
[2026-05-27 02:10:03] INFO  Run started: run_20260527_021003
[2026-05-27 02:10:03] INFO  Loading environment from .env
[2026-05-27 02:10:03] INFO  LLM provider configured: base_url=https://api.example.com/v1, model=xxx
[2026-05-27 02:10:04] INFO  Loading input/project_context.json
[2026-05-27 02:10:04] INFO  Loaded 5 members
[2026-05-27 02:10:04] INFO  Loaded 8 weeks: 2026-W18 to 2026-W25
[2026-05-27 02:10:08] INFO  Selected mode: dimensions_reviewers
[2026-05-27 02:10:20] INFO  Auto-selected 5 job-focused dimensions
[2026-05-27 02:10:20] INFO  Building comparison pairs
[2026-05-27 02:10:20] INFO  Week 2026-W18: 10 pairs, 0 automatic, 10 require LLM
[2026-05-27 02:10:20] INFO  Created 16 LLM batches with concurrency=3
[2026-05-27 02:10:21] INFO  Batch started: 2026-W18/hrbp/batch_001, pairs=10
[2026-05-27 02:10:41] INFO  Batch completed: 2026-W18/hrbp/batch_001, valid=10, errors=0, elapsed=20.3s
[2026-05-27 02:15:32] WARN  Batch partial errors: 2026-W22/business_lead/batch_001, valid=9, errors=1
[2026-05-27 02:16:10] INFO  Scoring completed
[2026-05-27 02:16:11] INFO  Reports written: report.md, report.html
[2026-05-27 02:16:11] INFO  Run completed: comparisons=160, errors=1
```

`run.log` 记录：

- 启动和结束
- 环境变量读取状态，不记录 API Key
- 输入文件读取结果
- 校验警告
- 用户选择的模式
- 维度生成/选择情况
- 每周 pair 数量
- 自动判定数量
- LLM 批次数量
- 每个批次开始、完成、失败、重试
- 计分和报告输出

### `llm_interactions.jsonl`

机器可读的大模型交互日志。

每条记录对应一次 LLM 调用。

字段：

```json
{
  "timestamp": "2026-05-27T02:10:21",
  "interaction_id": "llm_000001",
  "run_id": "run_20260527_021003",
  "type": "batch_comparison",
  "mode": "reviewers",
  "reviewer": "hrbp",
  "week_id": "2026-W18",
  "batch_id": "2026-W18__hrbp__batch_001",
  "prompt_template": "compare_as_hrbp_batch.md",
  "pairs": [
    {
      "pair_id": "2026-W18__hrbp__M001__M002",
      "a": "M001",
      "b": "M002"
    }
  ],
  "request": {
    "base_url": "https://api.example.com/v1",
    "model": "xxx",
    "temperature": 0,
    "timeout_seconds": 120
  },
  "rendered_prompt": "...",
  "raw_response": "...",
  "parsed_response": {
    "comparisons": []
  },
  "elapsed_seconds": 20.3,
  "success": true,
  "error": null
}
```

注意：

- 不记录 API Key
- 保存完整 `rendered_prompt`
- 保存完整 `raw_response`

### `comparisons.jsonl`

每条记录对应一场两两比较。

字段：

```json
{
  "timestamp": "2026-05-27T02:10:41",
  "run_id": "run_20260527_021003",
  "week_id": "2026-W18",
  "mode": "reviewers",
  "reviewer": "hrbp",
  "pair_id": "2026-W18__hrbp__M001__M002",
  "member_a": {
    "member_id": "M001",
    "name": "张伟",
    "role": "项目经理"
  },
  "member_b": {
    "member_id": "M002",
    "name": "李娜",
    "role": "A组组长"
  },
  "winner": "A",
  "score_a": 1,
  "score_b": 0,
  "confidence": "medium",
  "reason": "A本周推进关键风险闭环更直接",
  "called_llm": true,
  "automatic_reason": null,
  "batch_id": "2026-W18__hrbp__batch_001",
  "is_error": false,
  "error": null
}
```

自动判负示例：

```json
{
  "winner": "B",
  "score_a": 0,
  "score_b": 1,
  "reason": "自动判定：member_a_missing_report_and_speech",
  "called_llm": false,
  "automatic_reason": "member_a_missing_report_and_speech"
}
```

### `errors.jsonl`

每条记录对应一个异常。

包括：

- 输入校验异常
- 维度生成异常
- LLM 调用异常
- 批次失败
- 批次部分 pair 缺失
- 返回格式错误
- 成员 ID 不匹配

字段：

```json
{
  "timestamp": "2026-05-27T02:15:32",
  "run_id": "run_20260527_021003",
  "level": "ERROR",
  "stage": "comparison_parse",
  "week_id": "2026-W22",
  "reviewer": "business_lead",
  "batch_id": "2026-W22__business_lead__batch_001",
  "pair_id": "2026-W22__business_lead__M003__M005",
  "message": "Missing comparison result for pair",
  "details": {
    "expected_pair_id": "2026-W22__business_lead__M003__M005"
  }
}
```

### `run_snapshot.json`

保存本次运行的关键上下文，便于复盘。

内容：

```json
{
  "run_id": "run_20260527_021003",
  "started_at": "2026-05-27T02:10:03",
  "analysis_mode": "dimensions_reviewers",
  "input_dir": "input",
  "output_dir": "output/runs/run_20260527_021003",
  "member_count": 5,
  "week_count": 8,
  "llm": {
    "base_url": "https://api.example.com/v1",
    "model": "xxx"
  },
  "constants": {
    "concurrency": 3,
    "max_retries": 3,
    "max_pairs_per_llm_call": 10,
    "timeout_seconds": 120,
    "temperature": 0
  }
}
```

不保存 API Key。

## 控制台进度输出

控制台输出应比 `run.log` 更简洁，但要能看出程序正在做什么。

建议格式：

```text
Run: run_20260527_021003
Input: 5 members, 8 weeks
Mode: 4 - 绩效维度 + 评价官比较

[1/6] Loading input ... done
[2/6] Generating job-focused dimensions ... done
[3/6] Building comparison batches ... 16 batches
[4/6] Running LLM batches with concurrency=3
      completed 1/16: 2026-W18 / HRBP / batch_001 / valid=10 errors=0
      completed 2/16: 2026-W18 / Business Lead / batch_001 / valid=10 errors=0
      completed 3/16: 2026-W19 / HRBP / batch_001 / valid=9 errors=1
[5/6] Scoring rankings ... done
[6/6] Rendering reports ... done

Completed.
Report: output/runs/run_20260527_021003/reports/report.html
Errors: 1
```

控制台必须显示：

- run_id
- 成员数、周次数
- 当前分析模式
- 维度生成或选择状态
- LLM 批次总数
- 已完成批次数
- 每个批次的有效结果数和错误数
- 最终报告路径
- 错误数量

控制台不显示：

- 完整 prompt
- 原始模型响应
- API Key

## 标准输入结构

### `project_context.json`

```json
{
  "project_background": "项目背景、目标、周期、交付物、成功标准。",
  "department_background": "部门、岗位、团队协作方式、评价时需要考虑的岗位差异。",
  "analysis_note": "评价时需结合岗位职责、任务难度、协作依赖和项目阶段，不只按完成量评价。"
}
```

### `members.json`

```json
[
  {
    "member_id": "M001",
    "name": "张伟",
    "role": "项目经理",
    "responsibilities": "喜欢制定详细计划，每日跟进进度",
    "profile": {
      "experience": "8年项目管理经验，擅长创意项目统筹",
      "skills": ["项目管理", "创意构思", "团队协调"],
      "strengths": ["全局观强", "资源调配能力好"],
      "weaknesses": ["进度把控有时不够果断", "在高压下容易焦虑"]
    }
  }
]
```

### `weeks/*.json`

```json
{
  "week_id": "2026-W18",
  "start_date": "2026-05-01",
  "end_date": "2026-05-01",
  "reports": [
    {
      "member_id": "M001",
      "member_name": "张伟",
      "content": "本周周报全文"
    }
  ],
  "meetings": [
    {
      "title": "项目周会",
      "participants": ["M001", "M002"],
      "speeches": [
        {
          "member_id": "M001",
          "member_name": "张伟",
          "content": "会议发言全文"
        }
      ]
    }
  ]
}
```

## 待实现顺序

建议实现顺序：

1. 目录和数据模型
2. `.env` 读取
3. 输入读取和校验
4. 运行日志和控制台进度
5. prompt 加载
6. LLM 客户端
7. 维度生成
8. pair 构造和缺材料规则
9. 批量比较执行
10. 计分
11. 报告生成
12. 端到端验证
