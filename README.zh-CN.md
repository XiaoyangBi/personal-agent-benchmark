# Personal Agent Benchmark

[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![代码 MIT](https://img.shields.io/badge/code-MIT-green)](LICENSE)
[![数据 CC BY 4.0](https://img.shields.io/badge/data-CC%20BY%204.0-orange)](LICENSE-DATA)
[![合成数据](https://img.shields.io/badge/data-synthetic-lightgrey)](#概览)

[English](README.md) · **简体中文**

> 面向个人助理的合成评测集：10 个合成人物，每人 63 个检查点，四种上下文条件，离线确定性判分，并提供可复现的五模型排行榜。

**目录：** [概览](#概览) · [规模一览](#规模一览) · [评测维度](#评测维度) · [评测协议](#评测协议) · [数据集](#数据集) · [仓库结构](#仓库结构) · [快速开始](#快速开始) · [排行榜](#排行榜) · [可复现性](#可复现性) · [范围与局限](#范围与局限) · [引用](#引用) · [许可](#许可)

---

## 概览

本评测集检验助理能否正确使用用户历史、持续推进任务，以及在没有授权时保持克制。每个检查点包含触发话术、证据 session、环境状态与可执行断言。判分离线且确定性：以固定词表、结构化检查与工具参数规则核对结构化回复，不使用模型做裁判。

仓库提供完整题库、判分规则、运行器、已保存的模型回复，以及五家 API 模型在十个人物上的单轮评测结果。GPT 运行时为独立轨道，提供分母不同的三轮稳定性快照，不进入 API 排行榜。

所有人物、对话、工具环境、canary 与结果均为合成数据，不对应真实个人、真实记忆或真实业务记录。

## 规模一览

| 项目 | 数值 |
|---|---|
| 人物 | 10 个（合成，每人 23 个 session） |
| 每人检查点 | 63 |
| 上下文条件 | C0、C1、C2、C3 |
| 每模型完整单轮条目 | 63 × 4 × 10 = 2,520 |
| 断言规则 | 十份 `assertions.json` 共 1,540 条 |
| 回复 schema | `text`、`payload`、`citations`、`tool_calls` |
| 判分 | 离线确定性，无 LLM 裁判 |
| 运行依赖 | 仅 Python 标准库 |

## 评测维度

| 编号 | 维度 | 测什么 |
|---|---|---|
| D1 | 记忆 Memory | 事实写入、更新、召回与主动召回 |
| D2 | 推进 Focus | 目标还原、阻碍响应、可打断性、合理放弃 |
| D3 | 克制 Restraint | 越权、过度确认、打扰、谄媚 |
| D4 | 表达 Writing | 对外代笔、对内整理、表达协助 |
| D5 | 呈现 Rich UI | 卡片与按钮的 schema、呈现、行为、克制 |
| D6 | 纵向一致 Longitudinal | 跨月尺度的偏好漂移、关系连续性、记忆置信度 |
| D7 | 环境经验 Environment | 工具与环境状态的使用、边界、失败处理 |

一个检查点可归属多个维度，`data/persona-XX.json` 的 `dim` 字段以 `D1/D3` 形式记录复合归属。完整定义见 [docs/specification.md](docs/specification.md)。

## 评测协议

每个检查点在四种条件下各运行一次。条件间的差异用于区分检索失败与推理失败。

| 条件 | 输入 | 用途 |
|---|---|---|
| C0 | 仅当前 session | 无记忆下界，识别不依赖记忆的题目 |
| C1 | 当前 session + 指定证据 session | oracle 条件，排除检索变量 |
| C2 | 截至当前时点的全量历史，8000 token 字符估算预算 | 全量上下文对照；截断情况以结果元数据为准 |
| C3 | 当前 session + top-3 朴素检索记忆 | 评测记忆检索与读取表现 |

上下文构建、检索与预算实现见 `persona-01-linzhou/runner/conditions.py` 与 `memory.py`，协议说明见 [docs/protocol.md](docs/protocol.md)。工具为模拟协议，不执行真实下单、发消息或文件操作。

一个检查点通过等于该题全部规则通过。规则为词表、结构与工具参数检查，对语义质量只是弱代理，详见[范围与局限](#范围与局限)。

## 数据集

| 路径 | 内容 |
|---|---|
| `persona-XX-*/profile.md` | 合成人物设定 |
| `persona-XX-*/data/persona-XX.json` | 检查点、埋点、干扰项、目标事实、canary |
| `persona-XX-*/data/sessions.json` | 23 个 session 的用户话术 |
| `persona-XX-*/data/assertions.json` | 排行榜使用的逐题判分规则 |
| `persona-XX-*/data/dry_run_replies.json` | 用于反验规则的标准 fixture |
| `persona-XX-*/results/dry-run.json` | 四条件 fixture 链路验收，**不是**模型成绩 |
| `persona-XX-*/results/api-v2-nothink-<模型>.json` | 正式单轮模型结果 |

`persona-01-linzhou` 另保留 `data/assertions-v3.json`（108 条规则）与 GPT 运行时冻结输入和回复。该量尺分母不同，不可与 API 排行榜混排。63 题索引见 [docs/checkpoint-index.md](docs/checkpoint-index.md)，人物建设与校验见 [docs/personas.md](docs/personas.md) 和 [docs/persona-validation.json](docs/persona-validation.json)。

## 仓库结构

```
personal-agent-benchmark/
├── README.md                      # 英文主版
├── README.zh-CN.md                # 本文件
├── LICENSE                        # 代码 MIT
├── LICENSE-DATA                   # 数据与评测材料 CC BY 4.0
├── docs/
│   ├── specification.md           # 维度、判分、数据结构（中文）
│   ├── protocol.md                # 四条件协议（中文）
│   ├── checkpoint-index.md        # 63 题索引
│   ├── personas.md                # 人物导航
│   ├── api-v2-nothink-ranking.md/json      # 排行榜
│   ├── api-v2-nothink-validation.json     # 完整性与复算报告
│   ├── api-v2-nothink-sensitivity.json    # 四种口径敏感性
│   ├── model-results.md/json      # 历史 persona-01 实验索引
│   ├── run-inventory.json         # 全部结果文件及源 SHA-256
│   └── trace-availability.json    # trace 可得范围
├── persona-01-linzhou/            # 原有人物，同时承载共享 runner
│   ├── runner/                    # 条件、断言、执行、重放
│   ├── data/                      # 题库与判分规则
│   └── results/                   # 回复、attempt、suite、pilot 归档
├── persona-02-xutang/ … persona-10-guyao/
└── tools/
    ├── evaluation/                # 编排、排名、敏感性、校验
    ├── personas/                  # 人物生成与题库校验
    └── publication/               # 发布索引与一致性检查
```

## 快速开始

复现已发布结果所需的材料全部在仓库内，无需 API 密钥、网络访问或第三方依赖。

```bash
git clone https://github.com/XiaoyangBi/personal-agent-benchmark.git
cd personal-agent-benchmark

# 从已保存回复复算排行榜并核对完整性
python3 tools/evaluation/validate_api_suite.py
python3 tools/evaluation/rank_api_suite.py --allow-partial
python3 tools/evaluation/sensitivity_api_suite.py

# 校验题库与发布快照
python3 tools/personas/validate_bundle.py --require-dry-run
python3 tools/publication/validate_release.py
```

评测自己的系统见 `tools/evaluation/run_api_suite.py --help`，需自行配置模型凭据，且不要写入仓库。不调用模型即可验证判分链路时，按 [persona-01-linzhou/runner/README.md](persona-01-linzhou/runner/README.md) 使用 dry-run 模式。

## 排行榜

五家 API 模型、十个人物、单轮。排名只统计五家均有有效回复的 2,488 条，排除 32 条无共同有效回复的条目。指标为各人物 `assertions.json` 下的 pooled 通过率。

| 名次 | 模型 | 通过数 | 通过率 |
|---:|---|---:|---:|
| 1 | hy4-preview | 1,311 / 2,488 | 52.69% |
| 2 | deepseek-v4-flash | 1,237 / 2,488 | 49.72% |
| 3 | glm-5.3-flash | 1,234 / 2,488 | 49.60% |
| 4 | mimo-v2.6-flash | 1,199 / 2,488 | 48.19% |
| 5 | minimax-m3.1-flash | 1,122 / 2,488 | 45.10% |

完整报告见 [docs/api-v2-nothink-ranking.md](docs/api-v2-nothink-ranking.md)。这是解码配置受控下的任务表现对比，不是通用模型能力榜单，也不是显著性检验。

## 可复现性

- **只计有效回复**：`text` 为字符串，`payload`、`citations`、`tool_calls` 为列表，无 `error`，且 `score.passed` 非空。传输错误、空响应、缺结构化字段、整题未写入属于技术无效项，不按 0 分计，也不进入共同分母。
- **首份有效保留**：后续 attempt 只补缺失或技术无效的 key，已有有效回复不因分数高低被替换。
- **四种口径敏感性**：共同有效分母、全 2,520 分母且无效按 0、各家自身有效分母、可恢复回复规范化后计入，名次顺序完全一致。见 [docs/api-v2-nothink-sensitivity.json](docs/api-v2-nothink-sensitivity.json)。
- **解码配置**：DeepSeek、GLM、Hy4、MiMo 使用非推理输出；MiniMax 因网关在关闭思考时返回不可解析结构，使用标准输出。配置逐家验证，但仍是混杂因素。
- **轨道分离**：GPT 走 WorkBuddy 运行时独立轨道，仅作描述性参照，不进入 API 主榜，不作跨环境显著性结论。
- **归档运行**：废弃 pilot、限流试跑与标准模式首轮放在 `persona-*/results/pilot/`，不并入主榜；`dry-run.json` 是 fixture 链路验收。
- **trace 边界**：结构化上下文、回复与工具调用已保存；完整底层执行日志、实时读取证据与真实工具副作用未取得。见 [docs/trace-availability.json](docs/trace-availability.json)。

三个评测脚本只读已保存结果，不调用模型。`validate_api_suite.py` 会独立复算分数，并交叉核对无效项分类、首份有效保留与已发布排名。

## 范围与局限

- 十个人物共享 63 类场景以保证覆盖可比，属于扩展题集而非十次独立采样，不能据此计算显著性。
- 固定断言对语义质量、谄媚与文风只是弱代理；历史规则修正记录在结果元数据中。
- 主榜为**单轮**，不含重复采样方差。基于合成人物的 bootstrap 区间只衡量人物敏感性，不代表模型差异显著。
- 早期 58 题与 63 题版本、不同断言版本、重试合并结果、pilot 轨道、运行时与 API 轨道均分开保留；比较前必须核对分母与量尺。
- GPT 运行时完整底层执行 trace 未取得，结构化输入输出不冒充完整 trace。
- 公开快照截至 2026-11-04，是特定题集与解码配置下的观察值，不是已验收的通用能力基准。

## 引用

```bibtex
@misc{personal_agent_benchmark_2026,
  title  = {Personal Agent Benchmark: A Synthetic Rule-Scored Evaluation Suite},
  author = {XiaoyangBi},
  year   = {2026},
  url    = {https://github.com/XiaoyangBi/personal-agent-benchmark}
}
```

相关工作：[LongMemEval](https://arxiv.org/abs/2410.10813)（ICLR 2025）的 oracle 证据设计；四条件协议沿用该思路。

## 许可

- **代码**（`tools/`、`runner/`、脚本）：[MIT](LICENSE)。
- **数据与评测材料**（`persona-*/data/`、`persona-*/results/`、`docs/`、`profile.md`、报告）：[CC BY 4.0](LICENSE-DATA)。

使用数据需署名。全部数据为合成数据，不含个人信息。覆盖范围见 [LICENSE-DATA](LICENSE-DATA)。
