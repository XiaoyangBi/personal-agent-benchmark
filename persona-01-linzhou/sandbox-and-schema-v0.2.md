# 工具沙盒、输出协议与评测条件 v0.2

替代 v0.1 的 sandbox-and-schema.md。v0.1 保留，本文件为当前执行版本。
依据：LongMemEval V1 的 oracle 设计与证据接地，LongMemEval V2 的 Insert-Query-Reader 分离与延迟指标，AgentRunbook-C V2 的检索经验固化。

## 1. 四条件评测协议

每个检查点在四种条件下各跑一次，判读矩阵决定失败归因。四个条件共用同一份 session 数据、同一套工具、同一渲染器。

| 条件 | 输入给 agent 的内容 | 用途 |
|---|---|---|
| C0 无记忆 | 当前 session | 下界。C0 答对说明题目不依赖记忆，进废题流程 |
| C1 oracle | 当前 session + 该检查点关联的证据 session，其余不给 | 排除检索变量，只看推理与表达 |
| C2 全量上下文 | 全部历史 session 按时间顺序拼接，超预算按时间倒序截断 | 检验硬塞能否顶替记忆机制 |
| C3 完整 agent | 正常记忆机制 | 被测结果 |

判读矩阵：

| C0 | C1 | C3 | 归因 | 报告标签 |
|---|---|---|---|---|
| 错 | 对 | 错 | 记忆写入或检索失败 | 记忆失败 |
| 错 | 错 | 错 | 推理或表达能力不足 | 能力失败 |
| 对 | 对 | 错 | 不依赖记忆也能答，带记忆反而更差 | 记忆污染 |
| 错 | 对 | 对 | 正常 | 有效记忆 |
| 对 | 任意 | 任意 | 题目无效 | 废题 |

C2 强制记录截断情况：

```
{"condition": "C2", "sessions_total": 20, "sessions_included": 14,
 "tokens_included": 48210, "truncated": true, "truncate_policy": "time_desc_keep_latest"}
```

不记录截断的 C2 分数不可与其他运行比较。

## 2. 输出协议 v0.2

每轮回复结构：

```
reply = {
  text: string,                 // 正文，必填
  payload: component[],         // 富交互组件，纯文字能答的必须为空
  citations: citation[]         // 证据引用，D1 类检查点必填
}

citation =
  | { type: "session", id: string, quote?: string }
  | { type: "plant",   id: string }
  | { type: "none",    reason?: string }
```

引用规则：

| 规则 | 说明 | 违反后果 |
|---|---|---|
| R1 | D1 类检查点的 citations 不得为空 | M1.8 记 0 |
| R2 | 引用 id 必须真实存在于历史，禁止编造 | 计入 M1.9 扣分 |
| R3 | 弃答题必须给 none，或写"历史未提及" | 编造内容即 M1.7 记 0 |
| R4 | 答案对但引用错，记为侥幸命中 | M1.9 扣分，报告单列 |
| R5 | 引用对但答案错，单独计数 | 用于定位推理问题，不计入召回 |

引用对召回的计算口径：应引用证据集合取自检查点的 evidence 字段，命中数与总数之比为 M1.8，全部引用中正确引用占比为 M1.9。

## 3. UI payload schema

与 v0.1 一致，三种组件，不新增。改动一处：action 增加 `requires_confirm` 布尔字段，由渲染器决定是否先弹确认，模型不能靠"加个确认按钮"掩饰越权。

```
card   = { type:"card", title, fields:[{label,value}], actions:[action] }   // actions 最多 2 个
list   = { type:"list", items:[{title, subtitle?}] }
confirm= { type:"confirm", summary, actions:[confirmAction, cancelAction] }

action = {
  id, label, style:"primary"|"default"|"danger",
  effect: {tool, params} | {intent:"edit"},
  requires_confirm: bool
}
```

硬规则不变：effect 必须可执行；正文与卡片信息不得矛盾；一句话能答的不许上卡片；confirm 只用于不可逆高代价动作。

## 4. 性能字段

每条运行记录追加以下字段，进报告附录，不进维度分：

| 字段 | 含义 | 采集方式 |
|---|---|---|
| first_token_ms | 首个 token 延迟 | 运行时打点 |
| turn_latency_ms | 整轮完成延迟 | 运行时打点 |
| confirm_wait_ms | 等待用户确认的时长 | 沙盒计时 |
| tokens_in / tokens_out | 输入输出 token | 模型返回用量 |
| tool_calls | 工具调用次数 | 沙盒计数 |
| est_cost_usd | 估算成本 | 单价 × 用量 |

主动性曲线（本项目自研指标，V1 与 V2 均无）：

- 横轴：每 100 个 session 的主动发起次数
- 纵轴：有效提醒率（M3.4）
- 每个被测模型一个点，连线形成前沿
- 用途：回答"多主动才划算"，比单一打扰次数更有解释力

## 5. 运行时隔离

| 措施 | 做法 |
|---|---|
| 物理隔离 | 沙盒只挂载 sessions 与工具，不挂载 checkpoints、rubric、本文件 |
| 不透明 id | session 与埋点对外用短码，如 a7f3、b2e1，检查点编号不出现在沙盒 |
| 答案隔离 | 期望行为、标准答案、判读矩阵全部留在评测侧 |
| canary | 每个 persona 一条唯一字符串，检测是否进入输出或训练数据 |
| 元数据切断 | 查询接口只接收问题文本与可选图片，不接收题型、答案、gold 任何字段 |

## 6. 与 v0.1 的差异

| 项 | v0.1 | v0.2 |
|---|---|---|
| 评测条件 | 三条件，无 oracle | 四条件，含 oracle 与判读矩阵 |
| 输出结构 | text + payload | text + payload + citations |
| 性能指标 | 无 | 6 个字段 + 主动性曲线 |
| 防泄漏 | 仅训练集 canary | 运行时物理隔离 + 不透明 id + 元数据切断 |
| C2 截断 | 不记录 | 强制记录，否则分数不可比 |
