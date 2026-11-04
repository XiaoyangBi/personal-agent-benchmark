# 五模型 × 十人物 API 单轮排名

统一使用各人物 `assertions.json` 离线复算，只统计五家共同有效样本。DeepSeek、GLM、Hy4、MiMo 使用非推理输出；MiniMax 使用标准输出，因为网关在关闭思考时返回不可解析的结构。解码模式按模型验证但仍是混杂因素，结果是配置受控的任务表现对比，不是纯推理能力实验。主榜不包含 GPT 运行时，也不把 fixture 或技术错误按 0 分充数。

共同样本：2488 / 2520，排除 32 个无共同有效回复的条目。每模型目标 2520 条，每人物 252 条，单轮。

无效项口径：传输错误、空响应、缺结构化字段、整题未写入一律不计 0 分，也不计入分母；只从五家共同有效样本中剔除。分项数量见 `docs/api-v2-nothink-validation.json`。

| 排名 | 模型 | 通过数 | 通过率 | 人物间SD | 人物聚类bootstrap 95%区间 | 逐剔人物名次范围 |
|---:|---|---:|---:|---:|---:|---:|
| 1 | Hy4 (`hy4-preview`) | 1311/2488 | 52.69% | 4.31% | 51.03%–55.75% | 1–1 |
| 2 | DeepSeek (`deepseek-v4-flash`) | 1237/2488 | 49.72% | 4.35% | 47.58%–52.58% | 2–3 |
| 3 | GLM (`glm-5.3-flash`) | 1234/2488 | 49.60% | 3.65% | 48.04%–52.01% | 2–3 |
| 4 | MiMo (`mimo-v2.6-flash`) | 1199/2488 | 48.19% | 4.32% | 45.83%–50.85% | 4–4 |
| 5 | MiniMax (`minimax-m3.1-flash`) | 1122/2488 | 45.10% | 3.88% | 43.46%–47.69% | 5–5 |

## 分条件通过率

| 模型 | C0 | C1 | C2 | C3 |
|---|---:|---:|---:|---:|
| Hy4 | 26.35% | 64.29% | 62.86% | 58.25% |
| DeepSeek | 25.87% | 59.52% | 59.21% | 54.29% |
| GLM | 29.05% | 60.39% | 55.36% | 53.61% |
| MiMo | 29.21% | 55.89% | 54.29% | 53.02% |
| MiniMax | 24.44% | 53.81% | 51.19% | 51.03% |

## 分维度通过率

| 维度 | Hy4 | DeepSeek | GLM | MiMo | MiniMax |
|---|---:|---:|---:|---:|---:|
| D1 | 72.82% | 69.66% | 65.43% | 67.64% | 64.48% |
| D2 | 53.61% | 49.17% | 40.78% | 35.83% | 43.61% |
| D3 | 20.79% | 16.57% | 20.81% | 16.62% | 15.73% |
| D4 | 58.13% | 61.75% | 65.35% | 62.65% | 52.71% |
| D5 | 46.13% | 48.21% | 49.85% | 49.40% | 52.54% |
| D6 | 58.95% | 50.31% | 50.46% | 45.99% | 37.96% |
| D7 | 55.46% | 47.13% | 51.45% | 52.87% | 41.67% |

## 分人物通过率

| 人物 | Hy4 | DeepSeek | GLM | MiMo | MiniMax |
|---|---:|---:|---:|---:|---:|
| persona-01-linzhou | 64.68% | 60.71% | 59.50% | 58.00% | 55.78% |
| persona-02-xutang | 49.21% | 46.83% | 48.57% | 43.25% | 43.65% |
| persona-03-chenyu | 52.78% | 50.79% | 51.00% | 47.62% | 44.84% |
| persona-04-suhe | 50.40% | 45.63% | 47.39% | 45.24% | 42.46% |
| persona-05-zhengbei | 51.59% | 50.79% | 48.40% | 45.63% | 43.65% |
| persona-06-linlan | 52.38% | 49.60% | 47.01% | 50.79% | 44.05% |
| persona-07-zhouheng | 50.40% | 49.21% | 47.60% | 47.62% | 42.23% |
| persona-08-tangning | 52.38% | 45.24% | 49.60% | 46.03% | 45.24% |
| persona-09-luochen | 52.78% | 50.00% | 48.80% | 51.59% | 45.24% |
| persona-10-guyao | 52.78% | 48.41% | 48.41% | 45.24% | 44.05% |

## 逐题判定差异

`a_only` / `b_only` 是共同样本中仅一方通过的条目数；两者不等同于统计显著差异。

| 模型A | 模型B | 仅A通过 | 仅B通过 | 同过 | 同败 |
|---|---|---:|---:|---:|---:|
| DeepSeek | MiniMax | 286 | 171 | 951 | 1080 |
| DeepSeek | GLM | 199 | 196 | 1038 | 1055 |
| DeepSeek | Hy4 | 148 | 222 | 1089 | 1029 |
| DeepSeek | MiMo | 201 | 163 | 1036 | 1088 |
| GLM | MiniMax | 296 | 184 | 938 | 1070 |
| GLM | Hy4 | 162 | 239 | 1072 | 1015 |
| GLM | MiMo | 194 | 159 | 1040 | 1095 |
| Hy4 | MiniMax | 333 | 144 | 978 | 1033 |
| Hy4 | MiMo | 258 | 146 | 1053 | 1031 |
| MiMo | MiniMax | 264 | 187 | 935 | 1102 |

## 口径与限制

- One API round per model; no stochastic repeat variance or significance claim.
- DeepSeek, GLM, Hy4 and MiMo use non-thinking output. MiniMax uses standard output because the gateway returns an unparsable payload when thinking is disabled. Decoding mode is per-model validated but remains a confound.
- Fixed lexical, structural and tool assertions are weak proxies for semantic quality.
- Synthetic personas share scenario archetypes and are not independent real-user samples.
- C3 uses the naive bigram retriever, not a production memory system.
- GPT runtime results are a separate track and are excluded from this API ranking.
- Items with no valid reply from any model are excluded from the common denominator rather than scored as failures.
- Token usage and latency are descriptive; no price table or cost ranking is inferred.

人物聚类区间由固定随机种子的5000次人物重采样得到；逐剔人物名次范围每次移除一个人物后重算总分与排名。它们用于观察合成人物敏感性，不是模型重复采样置信区间。
