# work-pair

工作配对与绩效评估实验仓库。当前仓库主要包含两部分能力：

- 使用 `MockWork` 生成虚拟项目过程数据，包括成员、任务、周报、周会、事件流和总结报告。
- 使用 `KPICalculate` 基于项目材料进行团队成员贡献度两两比较、维度比较和评价官比较，并输出 Markdown / HTML 报告。

仓库中也保留了若干已生成的示例报告，便于对照不同项目和不同评价模式的输出效果。

## 目录结构

```text
.
├── MockWork/          # 多 Agent 虚拟工作数据生成器
├── KPICalculate/      # 通用绩效分析 CLI
├── 合同管理软件/      # 合同管理软件项目的示例分析报告
└── 汉服营销/          # 汉服营销项目的示例分析报告
```

## 子项目说明

### MockWork

`MockWork` 用于根据项目背景生成一段虚拟项目周期内的工作数据。它会产出成员档案、任务池、周报、周会、任务变化事件、成员总结和最终报告。

常用运行方式：

```powershell
cd .\MockWork
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m mockwork
```

运行前需要在 `.env` 中配置 OpenAI 兼容接口：

```text
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://your-openai-compatible-endpoint/v1
OPENAI_MODEL=your-model-name
MOCKWORK_MAX_WORKERS=4
```

更多说明见 `MockWork/README.md`。

### KPICalculate

`KPICalculate` 用于读取项目材料，对团队成员在项目目标下的相对贡献进行分析。当前支持：

- 直接两两比较
- 绩效维度比较
- 评价官比较
- 绩效维度 + 评价官比较

常用运行方式：

```powershell
cd .\KPICalculate
Copy-Item .env.example .env
python .\main.py
```

运行前需要在 `.env` 中配置大模型接口：

```text
LLM_BASE_URL=https://api.example.com/v1
LLM_API_KEY=your-api-key
LLM_MODEL=your-model-name
```

默认输入目录为 `KPICalculate/input/`，输出目录为 `KPICalculate/output/`。每次运行会生成独立的 `run_YYYYMMDD_HHMMSS` 目录，并保存报告、日志、大模型交互记录和中间产物。

详细设计见：

- `KPICalculate/PROJECT.md`
- `KPICalculate/DESIGN.md`

## 示例报告

当前仓库包含两组示例项目报告：

- `合同管理软件/直接比较/`
- `合同管理软件/设置维度与不同岗位评价/`
- `汉服营销/双人比对/`
- `汉服营销/维度比对/`

每个示例目录通常包含：

- `report.md`
- `report.html`

可以直接打开 HTML 查看最终报告效果，也可以阅读 Markdown 版本了解结构化输出内容。

## 推荐工作流

1. 在 `MockWork` 中生成虚拟项目数据。
2. 将生成结果整理到 `KPICalculate/input/`。
3. 运行 `KPICalculate` 选择分析模式。
4. 查看 `KPICalculate/output/runs/` 中生成的报告和日志。
5. 将有代表性的输出整理为示例报告目录。

## 注意事项

- `.env` 文件包含密钥信息，不应提交到远程仓库。
- `.venv/`、`.idea/`、缓存目录和大体积运行产物通常不建议纳入版本控制。
- 大模型输出会受模型、提示词、项目材料质量和运行模式影响，报告结果适合作为分析辅助，不应作为唯一决策依据。
