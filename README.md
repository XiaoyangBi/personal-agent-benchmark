# Personal Agent Benchmark

面向个人助理的公开合成评测样例集，覆盖记忆、任务推进、克制、表达、界面呈现、时间推理和环境经验。包含 10 个合成人物的完整题目、四种上下文条件与判分规则，以及五家 API 模型在 10 个人物上的单轮完整评测结果和统一排名；persona-01 另保留 GPT 三轮运行时输入、回复、已有 trace 和稳定性统计。

> 本仓库的所有人物及其经历、对话、工具环境均为虚构数据，不对应真实个人或真实业务记录。不包含个人记忆、真实企业数据或账号凭据。

## 从哪里开始

| 要看什么 | 入口 |
|---|---|
| 评测目标、维度与协议 | [规格 v0.1](PersonalAgent评测集规格_v0.1.md)、[四条件协议](persona-01-linzhou/sandbox-and-schema-v0.2.md) |
| 10 个合成人物与建设状态 | [人物题库导航](docs/personas.md)、[扩展校验结果](docs/persona-validation.json) |
| persona-01 的 63 道题索引与原文 | [检查点索引](docs/checkpoint-index.md)、[结构化题库](persona-01-linzhou/data/persona-01.json) |
| 23 个 session 与人物设定 | [sessions.json](persona-01-linzhou/data/sessions.json)、[profile.md](persona-01-linzhou/profile.md) |
| 最新统一评分标准 | [assertions-v3.json](persona-01-linzhou/data/assertions-v3.json)、[断言引擎](persona-01-linzhou/runner/assertions.py) |
| 运行、检索、评分和复算代码 | [runner/](persona-01-linzhou/runner/README.md) |
| 五模型 × 十人物统一排名（本轮主榜） | [排名报告](docs/api-v2-nothink-ranking.md)、[机器可读](docs/api-v2-nothink-ranking.json) |
| 排名口径校验与敏感性分析 | [完整校验](docs/api-v2-nothink-validation.json)、[四种口径敏感性](docs/api-v2-nothink-sensitivity.json) |
| 全模型结果与报告 | [按模型查看结果](docs/model-results.md)、[results/](persona-01-linzhou/results/)、[材料导航](docs/data-guide.md) |
| GPT 三轮输入、回复与稳定性 | [gpt-runtime/](persona-01-linzhou/results/gpt-runtime/)、[三轮统计](persona-01-linzhou/results/gpt-runtime/stability-three-models.json) |
| 历次结果文件清单 | [run-inventory.json](docs/run-inventory.json) |
| 发布范围与历史口径 | [publication-manifest.json](docs/publication-manifest.json)、[项目变更记录](docs/project-history.md) |

## 当前题集与条件

每个人物的题集为 **63 个检查点 × 4 个条件 = 252 次调用/完整轮**。五家 API 模型已在 10 个人物上各完成一轮，正式轨道结果位于各人物 `results/api-v2-nothink-<模型>.json`，另有 `-attempt*.json` 技术重试记录和 `-suite.json` 编排清单。各人物还保留 `results/dry-run.json`，那是纯 fixture 链路验收，不是模型成绩。废弃的高并发 429 轨道、试跑与标准模式首轮已归入各人物 `results/pilot/`，不并入主榜。persona-01 的早期结果另含 58 题版本和已知 C1 缺陷版本，保留用于审计，不可与最新版本直接混排。

| 条件 | 输入 | 用途 |
|---|---|---|
| C0 | 当前 session | 无记忆下界，检查越权与题目依赖性 |
| C1 | 当前 session + 指定证据 session | oracle，排除检索变量 |
| C2 | 截至当前时点的历史，8000 token 字符估算预算 | 全量上下文对照；截断情况以结果元数据为准 |
| C3 | 当前 session + top-3 朴素检索记忆 | 评测记忆检索及读取表现 |

每题由结构化触发话术、证据 session、触发轮次、环境状态和多条规则组成。输出统一为 `text`、`payload`、`citations`、`tool_calls`。工具是模拟协议，不执行真实下单、发消息、删文件等动作。

## 评测覆盖

- 模型与运行方式：DeepSeek、MiniMax、混元 Hy4、GLM、MiMo 的 API 运行；GPT 的 WorkBuddy 运行时独立轨道。
- 结果：每题回复、模型声明的工具调用、上下文、判分明细、可用的性能字段、检索结果及归因。
- GPT：每题独立会话，三轮各 252 条有效回复；冻结输入与回复均逐条保存。
- 稳定性：同一量尺离线重放，报告样本标准差、极差、逐题判定翻转率及分条件结果；不是显著性检验。
- 历史研究：保留断言修正、授权与 omission、执行确认闸门、成本分析、横测报告和旧版实验，具体状态以各报告日期与口径为准。

## 五模型 × 十人物单轮排名（api-v2-nothink）

统一使用各人物 `assertions.json` 离线复算，只统计五家共同有效样本 **2488 / 2520**，排除 32 个无共同有效回复的条目。单轮，不含重复采样，不是显著性检验。

| 排名 | 模型 | 通过数 | 通过率 |
|---:|---|---:|---:|
| 1 | 混元 Hy4 | 1311 / 2488 | 52.69% |
| 2 | DeepSeek | 1237 / 2488 | 49.72% |
| 3 | GLM | 1234 / 2488 | 49.60% |
| 4 | MiMo | 1199 / 2488 | 48.19% |
| 5 | MiniMax | 1122 / 2488 | 45.10% |

口径要点：

- DeepSeek、GLM、Hy4、MiMo 使用非推理输出；MiniMax 使用标准输出，因为网关在关闭思考时返回不可解析结构。解码模式按模型验证但仍是混杂因素，属于配置受控的任务表现对比，不是纯推理能力实验。
- 传输错误、空响应、缺结构化字段、整题未写入一律不按 0 分，也不计入分母；分项数量见校验报告。
- 用四种口径（共同有效、全分母无效记 0、各家自身有效分母、可恢复回复规范化后）复算，名次顺序完全一致。
- GPT 运行时是独立轨道，不进入这张 API 主榜；早期三轮稳定性快照与它分母、量尺不同，不可混排。
- 完整分条件、分维度、分人物与逐题差异见 [排名报告](docs/api-v2-nothink-ranking.md)。

## 三轮稳定性快照

统一 `assertions-v3`，GPT / Hy4 / MiMo 各三轮共同有效样本 **252 条**，C0-C3 各 63 条。SD 和极差单位为百分点。

| 模型 | 三轮通过数 | 平均通过率 | 样本 SD | 极差 | 平均两两判定翻转率 |
|---|---|---:|---:|---:|---:|
| GPT 运行时 | 161 / 155 / 166 | 63.76% | 2.19 | 4.37 | 9.79% |
| Hy4 API | 148 / 152 / 143 | 58.60% | 1.79 | 3.57 | 11.11% |
| MiMo API | 129 / 147 / 147 | 55.95% | 4.12 | 7.14 | 24.34% |

这只是观察值的描述性对比：运行时与 API 不是同一环境，不能解释为纯模型能力的显著性排名。三轮共同分母也不同于早期五家 API 的 251 条共同键。

## trace 的边界

本仓库区分四类记录：

1. **API 结构化结果**：输入上下文、回复、工具调用、判分、检索与性能字段，见各 `results/*.json`。
2. **GPT 运行时输入/输出**：`manifest.json`、`inputs/`、`replies/` 与 `r1-r3.json`，可重放固定评分。
3. **已保存的 trace 分析**：例如 GLM 的抽样 trace 分析文件。
4. **未取得的完整底层 trace**：GPT 子会话完整执行日志、实时读取证据、真实工具状态变更和端到端编排日志并不完整，不用结构化输入/输出冒充完整 trace。

因此，本仓库可以复核题目、输入、回复和固定断言分数；不能声称已经完成全量执行 trace 审计。所有缺数据项保持缺失或标注，不做补写。机器可读说明见 [trace-availability.json](docs/trace-availability.json)。

## 校验与复算

仅使用 Python 标准库：

```bash
python3 persona-01-linzhou/validate_cases.py
python3 persona-01-linzhou/runner/check_assertions.py
python3 persona-01-linzhou/runner/runtime_eval.py stability
python3 tools/personas/validate_bundle.py --require-dry-run
python3 tools/evaluation/rank_api_suite.py --allow-partial
python3 tools/evaluation/sensitivity_api_suite.py
python3 tools/evaluation/validate_api_suite.py
python3 tools/publication/validate_release.py
```

`rank_api_suite.py --allow-partial` 用共同有效样本重算并生成排名；`sensitivity_api_suite.py` 用四种口径验证名次；`validate_api_suite.py` 独立复算并交叉核对排名、无效项分类和首份有效保留。三者都只读已保存结果，不调用模型。重放真实模型需要自行配置模型服务凭据。不要把凭据写入仓库或提交到 Git。`results/` 中已经包含历史运行，不需要重新调用模型即可复核固定规则得分。

## 公开范围与版本说明

- 本仓库是截至 **2026-11-04** 的现有评测材料公开快照。五模型单轮主榜是特定题集、特定解码配置下的观察值，不是已验收的通用模型能力榜单。
- 固定断言多数为词表、结构化动作与规则检查，对语义、谄媚和代笔风格只是弱代理；历史上存在误判修正，见相应报告。
- 早期 58 题、63 题、不同断言版本、重试合并结果、429 pilot 轨道以及运行时/API 轨道均分开保留，比较时必须核对分母与量尺。
- persona-02～10 共享 63 类场景以保证覆盖可比，不是独立重复采样；各人物 `dry-run.json` 是 fixture 链路验收，不属于模型评测成绩。
- 主榜只覆盖 API 五家单轮；单轮结果不含随机重复采样方差，人物聚类 bootstrap 与逐剔人物名次范围仅衡量合成人物敏感性，不能当作模型显著性差异。
- 发布副本只替换本机绝对路径、企业文档链接及内部运行时引用；原评测目录不被修改。发布记录见 `docs/publication-manifest.json`。
- 未附带开源许可证；在另行明确许可证前，公开可见不等于授予任意复制、修改或再分发权利。
