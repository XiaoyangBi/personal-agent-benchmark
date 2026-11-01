# 四条件运行器（最小骨架）

## 目录与职责

```
runner/
├── build_sessions.py   剧本 md → data/sessions.json（只保留用户话术）
├── conditions.py       四条件上下文组装与预算截断
├── memory.py           C3 的记忆后端接口 + 朴素检索基线
├── assertions.py       规则断言引擎
├── runner.py           主流程：检查点 × 条件 → results.json
├── check_assertions.py 断言文件检查器（覆盖率、规则字段、turn 越界）
├── rescore.py          改口径后用已存回复离线重判，不重新调模型
├── aggregate.py        合并多次运行，按最新运行去重，统计异常题
└── report.py           results.json → results/report.html
```

## 调用流程

```
             ┌──────────────┐
             │ checkpoint   │  触发话术 + 证据 session + 断言规则
             └──────┬───────┘
                    │
     ┌──────────────┼──────────────┬──────────────┐
     ▼              ▼              ▼              ▼
    C0             C1             C2             C3
 当前session   当前+证据      全量历史截断    记忆后端检索
     │              │              │              │
     └──────────────┴──────┬───────┴──────────────┘
                           ▼
                  同一 system prompt
                  同一 reader 模型
                           ▼
                    reply JSON
              {text, payload, citations, tool_calls}
                           ▼
                    规则断言判定
                           ▼
              四格结果 → 判读矩阵归因
```

四种条件共用同一份 session 数据、同一个 system prompt、同一个模型、同一套断言，唯一变量是上下文。

| 条件 | 组装规则 | 用途 |
|---|---|---|
| C0 无记忆 | 只放当前 session | 下界，检验题目是否依赖记忆 |
| C1 oracle | 当前 session + 该题声明的证据 session | 排除检索变量 |
| C2 全量上下文 | 截至当前时点的全部历史，超预算从最旧开始丢 | 硬塞能否顶替记忆 |
| C3 完整 agent | 记忆后端返回相关 session + 当前 session | 被测结果 |

C2 截断写进结果：`truncated`、`dropped`、`tokens` 三个字段，不记录截断的分数不可比。

上下文截止规则：每个检查点声明触发话术在第几轮（`turn`），渲染当前 session 时只保留它之前的轮次。不这么做，同一 session 后面用户自己说出的答案会提前进入上下文，C0 会假性通过。这是第一轮实测发现并修掉的 bug。

C3 的记忆接口只有两个方法，换真实系统时不需要改主流程：

```python
memory.insert(session_id, text, index)
memory.query(question, k=3, before=index) -> [session_id]
```

骨架实现是字符二元组重合度排序，属于最弱基线。它的作用是把接口跑通，不代表真实记忆系统的水平。

## 判分

`data/assertions.json` 给每个检查点配一组规则，规则通过才算该题通过。支持的类型：

| 类型 | 判什么 |
|---|---|
| required_terms | 必含词，any 或 all |
| forbidden_terms | 禁词，出现即失败 |
| payload_empty / payload_max | 卡片该不该出、最多几张 |
| tool_called / tool_not_called | 工具调用，可限定参数前缀 |
| citations | 必须引用，或必须给 none |
| no_confirm_ask | 不得出现过度确认问句 |
| regex | 自定义正则 |

当前 58 个检查点全部接了断言，共 85 条规则，平均每题 1.5 条。规则类型分布：required_terms 45、forbidden_terms 20、payload_empty 5、tool_not_called 5、tool_called 3、no_confirm_ask 2、regex 2、payload_max 1、citations 1、payload_action 1。

## 判读矩阵

| C0 | C1 | C3 | 归因 |
|---|---|---|---|
| 错 | 对 | 对 | 有效记忆 |
| 错 | 错 | 对 | 记忆生效·oracle异常（需复查稳定性） |
| 错 | 对 | 错，且证据未召回 | 检索未命中 |
| 错 | 对 | 错，证据已召回 | 读取失败 |
| 错 | 错 | 错 | 能力失败 |
| 对 | 任意 | 错 | 记忆污染 |
| 对 | 对 | 对 | 废题（陷阱题除外） |

三条补充规则：

1. C3 的检索结果参与归因。先看记忆后端有没有把证据 session 召回，没召回记「检索未命中」，召回了但答错记「读取失败」。这两种失败的修法完全不同，一个改检索，一个改读取。
2. C2 与 C1 的差异单独记录，不覆盖主归因。`c2_conflict` 表示 oracle 能过但全量上下文过不了，`c2_tool_diff` 表示两条件的工具调用不同，`c2_text_sim` 是回复文本相似度。
3. 越权与工具差异单列，不改主归因。`c0_violation` 记录无记忆条件下直接调用的不可逆工具（order.create、message.send、file.delete），`c1_tools` / `c3_tools` / `tool_diff_c1_c3` 记录两条件的工具签名差异，`pollution` 存记忆污染的结构化证据（C0 通过、C3 失败、两者文本相似度）。主归因看 C3，C2 作为干扰信号挂在标签旁边。

非 D1 类检查点不参与归因，标为「非记忆题」，只看绝对分。

## C1 失败原因

oracle 条件下仍然失败，说明不是检索问题。除了记录失败规则，还给失败分三种行为模式：

| 模式 | 判定 | 含义 |
|---|---|---|
| 以工具查询代替回答 | C1 有工具调用且答案要素缺失 | 证据就在上下文里，模型仍选择查工具 |
| 否认上下文里的已知信息 | 回复含"没提过/不记得/没说过" | 读到了但判断成不存在 |
| 信息要素缺失或违规 | 其余情况 | 答案不完整或触碰禁词 |

这三种模式的修法不同：第一种要改提示或工具策略，第二种要改读取与判断，第三种要改断言或模型能力。报告里单列一张 C1 失败原因表。

## 断言检查

```bash
python3 check_assertions.py
```

检查八件事：58 个检查点是否都有断言、规则类型与必填字段、turn 是否越界、evidence 是否为合法 session、触发话术能否在剧本里找到、有没有空规则列表、工具名是否在清单内、正则能否编译。另外检查同一条断言里是否既要求又禁止同一词，以及 payload_action 的 intent 是否合法。当前结果：0 错误，1 条警告（CP21 的触发话术是剧本未写入的分支）。

## 结果结构与汇总

单个批次：

```
results/results.json
├── meta     运行 id、模式、模型、预算、条件、覆盖度
├── runs[]   每次运行：cp、session、dim、condition、context、reply、score、perf
└── matrix   cp → {C0..C3 通过与否, text, tool_calls, retrieval, attribution}
```

全量汇总：

```bash
python3 aggregate.py     # 合并所有 results*.json，按最新运行去重 → results/all.json
python3 report.py --input ../results/all.json --out ../results/report-all.html
```

`all.json` 多一个 `stats` 字段：模型侧异常题数与占比、含 C0 越权的合并口径、题目待修（废题）、陷阱未触发的题数与清单、标签分布、C0 越权题、C1 失败题与行为模式分布。

```bash
python3 make_summary.py   # 从 all.json 生成 results/summary.md
```

改断言口径后不要重跑模型，先离线重判：

```bash
python3 rescore.py --dry   # 只看变化
python3 rescore.py         # 写回历史结果
```

## 报告页

`results/report.html` 五块：顶部指标卡（运行数、通过数、覆盖率、记忆污染数）、判读矩阵表、维度通过率条、上下文成本表、失败明细。白底暖色，绿通过红失败。

## 接真实模型

```bash
export LME_BASE_URL=https://api.deepseek.com
export LME_API_KEY=...
export LME_MODEL=deepseek-flash
python3 runner.py --conditions C0,C1,C2,C3
```

也可以直接读本机模型配置，密钥不出现在命令行里：

```bash
python3 runner.py --model-config ~/.workbuddy/models.json
```

dry run 用 `data/dry_run_replies.json` 里的固定回复，只验证链路，不代表模型能力。

## 已知限制

1. 断言全部接上了，但多数是词表与工具调用断言，语义类判断（谄媚、代笔像不像本人）只能做到弱代理
2. 第一轮实测发现三个 harness 缺陷并已修：工具名靠模型自己编（已加工具清单）、环境状态不可见（已加 env 字段）、同 session 后续轮次泄露答案（已加 turn 截止）。修完之前的所有分数都不可比
3. CP21 的触发话术来自剧本分支，不在现有 session 里，检查器会持续报警；正式跑之前要把这句写进 S18
4. S08 剧本是浓缩版，已补 U3 用于 CP34，但整体仍偏短
5. 判读矩阵依赖四个条件都跑完，缺条件时不出归因
6. 早期单题单次运行快照没有方差估计；GPT、Hy4、MiMo三轮补跑与稳定性统计另见下节，任何单题结论仍受固定断言量尺限制

## 三模型三轮稳定性复算

```bash
python3 runtime_eval.py stability
```

- 输入：results/gpt-runtime/r1.json、r2.json、r3.json；EXTERNAL_FILES中Hy4、MiMo的前三轮文件。
- 各模型三轮使用同一assertions-v3.json离线重放，按(cp, condition)取九源共同有效键，不修复或覆盖原始回复。
- 输出：results/gpt-runtime/stability-three-models.json，含原始文件指纹、共同分母、逐轮通过数、均值、样本SD(ddof=1)、极差、三对翻转数/率、混合判定题比例、C0-C3分组和逐题矩阵。
- 当前共同分母252条，GPT通过数161/155/166、Hy4为148/152/143、MiMo为129/147/147。与五家API251交集口径区分。
- 完成自检：独立方差复算、逐题翻转与分条件加总、九源指纹、恒定输入和无效入参边界；格式调整后统计复跑一致。
- 仅描述观察到的稳定性，不将GPT运行时和API合并为同条件模型排名，不输出显著性、SE或未测得的延迟/成本指标。
