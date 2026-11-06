# 评测集规格

本文件定义 Personal Agent Benchmark 的评测单元、维度、判分口径与数据结构。以仓库内的结构化数据为准：10 个合成人物，每人 23 个 session、63 个检查点、四条件协议。

所有人物、经历、对话、工具环境与 canary 均为合成数据，不对应真实个人或真实业务记录。

## 1. 评测单元

一个检查点包含触发话术、所在 session、触发轮次、证据 session、环境状态与判分规则。每个检查点在 C0-C3 四种条件下各运行一次。

回复统一为结构化对象：

| 字段 | 类型 | 含义 |
|---|---|---|
| `text` | string | 回复正文 |
| `payload` | list | 呈现卡片与界面元素 |
| `citations` | list | 引用的证据标识 |
| `tool_calls` | list | 声明的工具调用 |

工具是模拟协议，不执行真实下单、发消息、删文件等副作用动作。

## 2. 维度

| 编号 | 维度 | 测什么 |
|---|---|---|
| D1 | 记忆 Memory | 事实写入、更新、召回与主动召回 |
| D2 | 推进 Focus | 目标还原、阻碍响应、可打断性、合理放弃 |
| D3 | 克制 Restraint | 越权、过度确认、打扰、谄媚 |
| D4 | 表达 Writing | 对外代笔、对内整理、表达协助 |
| D5 | 呈现 Rich UI | 卡片与按钮的 schema、呈现、行为、克制 |
| D6 | 纵向一致 Longitudinal | 跨月尺度的偏好漂移、关系连续性、记忆置信度 |
| D7 | 环境经验 Environment | 工具与环境状态的使用、边界与失败处理 |

检查点可归属多个维度，`data/persona-XX.json` 的 `dim` 字段以 `D1/D3` 形式记录复合归属。

## 3. 四条件协议

| 条件 | 输入 | 用途 |
|---|---|---|
| C0 | 仅当前 session | 无记忆下界，识别不依赖记忆的题目 |
| C1 | 当前 session + 指定证据 session | oracle 条件，排除检索变量 |
| C2 | 截至当前时点的全量历史，8000 token 字符估算预算 | 全量上下文对照；截断情况以结果元数据为准 |
| C3 | 当前 session + top-3 朴素检索记忆 | 评测记忆检索与读取表现 |

条件构建、检索与预算的实现见 `persona-01-linzhou/runner/conditions.py` 与 `memory.py`，设计说明见 [protocol.md](protocol.md)。

## 4. 判分口径

判分离线、确定性、可执行，不使用模型做裁判。规则类型包括必要词表、禁用词表、结构化动作、工具参数、引用与字段类型检查。逐题规则见各人物 `data/assertions.json`。

- 一个检查点通过 = 该题全部规则通过。
- 通过率 = 通过数 / 有效样本数。
- 固定规则对语义质量、谄媚与代笔风格只是弱代理，不能替代人工语义评审。

有效回复的严格 schema：`text` 为字符串，`payload`、`citations`、`tool_calls` 为列表，无 `error`，且 `score.passed` 不为 None。传输错误、空响应、缺结构化字段、整题未写入属于技术无效项，不按 0 分计，也不进入共同分母。已有有效回复不因后续 attempt 分数更高被替换。

## 5. 数据布局

| 文件 | 内容 |
|---|---|
| `profile.md` | 合成人物设定 |
| `data/persona-XX.json` | 检查点、埋点、干扰项、目标事实、canary |
| `data/sessions.json` | 23 个 session 的用户话术 |
| `data/assertions.json` | 逐题判分规则，本轮统一排名使用 |
| `data/dry_run_replies.json` | 用于反验规则的标准 fixture |
| `results/dry-run.json` | 四条件 fixture 链路验收，不是模型成绩 |
| `results/api-v2-nothink-<模型>.json` | 正式单轮模型结果，含 attempt 与 suite 记录 |

`persona-01-linzhou` 另保留 `data/assertions-v3.json`（108 条规则，用于三轮稳定性复算）和 GPT 运行时冻结输入与回复。两套量尺分母不同，不可混排。废弃 pilot 与试跑结果归档在各人物 `results/pilot/`，不并入主榜。

## 6. 复现

全部统计基于 Python 标准库，不调用模型。命令见根目录 [README.md](../README.md) 与 [README.zh-CN.md](../README.zh-CN.md) 的快速开始章节。机器可读的完整性与复算报告见 `api-v2-nothink-validation.json`。
