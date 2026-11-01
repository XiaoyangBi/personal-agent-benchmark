# 评测材料导航

## 一、题目与标准

最新版本使用 `persona-01-linzhou/data/persona-01.json` 中的 63 个检查点。每题记录维度、所属 session、难度、期望输出、指标与判分方式；具体触发话术、证据 session、环境状态及规则在同目录 `assertions-v3.json`。

历史 `assertions.json` 和带日期的备份保留用于追溯量尺变更。跨版本结果必须核对评分文件，不应只看通过率。

| 文件 | 内容 |
|---|---|
| `profile.md`、`timeline.md` | 合成人物与时间线 |
| `sessions-S01-S05.md` 等 | 23 个 session 的可读剧本 |
| `data/sessions.json` | 实际用于上下文组装的结构化剧本 |
| `data/persona-01.json` | 埋点、检查点、期望行为和指标 |
| `checkpoints-CP01-CP10.md` 等 | 部分检查点的可读定义与历史补定义 |
| `sandbox-and-schema*.md` | 输入输出协议、四条件和隔离规则 |
| `runner/assertions.py` | 固定规则执行逻辑 |
| `runner/check_assertions.py`、`validate_cases.py` | 结构、触发、证据、规则与词表检查 |

## 二、trace 与原始回复

`persona-01-linzhou/results/` 保存所有已有结果，不删除失败样本或旧版实验。

- `results/all-v2.json`：DeepSeek 63 题合并结果，252 条。
- `results/glm-v2/`、`hy4-v2/`、`hy4-preview/`：相应模型与轮次的 API 结果。
- `results/rep*-mimo.json`、`rep*-deepseek.json`、`rep*-minimax*.json`：多轮重复实验与补充运行。
- `results/v1-c1bug/`：已知 C1 缺陷的早期 58 题实验，只作历史追溯。
- `results/gpt-runtime/inputs/`：每题冻结的结构化消息，含 manifest 的输入指纹。
- `results/gpt-runtime/replies/`：GPT 每题、每轮独立回复。
- `results/gpt-runtime/r1.json`、`r2.json`、`r3.json`：GPT 三轮上下文、回复、工具调用和判分汇总。
- `results/gpt-runtime/transport-errors/`：技术失败与重试留档，不是按分数选答。
- `results/glm-v2/sampled_traces_analysis.json` 等：实际保存过的抽样 trace 分析。

结果 JSON 中的 `context`、`reply`、`tool_calls`、`score`、`perf`、`retrieval` 按各文件实际字段保留。模型返回的调用是模拟协议记录，不是已执行的真实业务动作。

未完整取得的底层执行日志、读取前完整输入证据、真实工具状态变化不在仓库内。`docs/trace-availability.json` 对可得范围作机器可读标记。

## 三、结果与统计

- `results/报告-MiMo横测与五家对比.md`：五家 API 的多轮结果与边界。
- `results/报告-P1-1方差与P2-1断言修正.md`：方差与断言修正。
- `results/gate-acceptance-report.md`、`results/results-v2-gate-deepseek.json`：授权后不可逆动作的确认闸门实验。
- `报告-P0-1授权与omission.md`：授权与遗漏问题。
- `results/gpt-runtime/stability-three-models.json`：三模型三轮统一量尺的共同样本、分条件统计和逐题判定矩阵。
- `runner/variance*.py`、`rank_robust.py`、`power_check.py`：已有方差、稳健性与功效分析代码。
- `runner/runtime_eval.py`：GPT 冻结输入准备、固定评分汇总和三轮稳定性复算。

主 README 只展示最新三模型三轮快照，不将其扩展成所有模型的统一排行榜。更完整的研究过程和历次口径变更见项目原 README 及各报告。

## 四、发布保真

`docs/publication-manifest.json` 记录发布范围、脱敏转换与源目录快照；`docs/run-inventory.json` 列出结果文件、模型、运行条数和源文件 SHA-256。发布后的 Git 提交和 Git 对象提供版本级完整性校验。

允许的发布转换仅有：

1. 本机绝对工作区路径替换为 `<workspace>`；
2. 企业文档链接替换为 `<removed-enterprise-document-link>`；
3. 内部运行时会话引用替换为 `<runtime-session-ref>`；
4. 人物档案补充合成数据声明；
5. 原 README 的规格文档相对路径适配新仓库结构；
6. 根目录新增导航、索引和说明文件。

原输入、回复、工具参数与评分规则不按分数修改。发布目录之外的原始文件保持不变。
