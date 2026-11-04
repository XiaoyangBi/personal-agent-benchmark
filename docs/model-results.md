# 按模型查看结果

## 本轮正式统一评测（五模型 × 十人物单轮）

正式轨道 `api-v2-nothink`：五家 API 模型在 10 个人物上各跑一轮，结果位于各人物 `results/api-v2-nothink-<模型>.json`。统一排名见 [排名报告](api-v2-nothink-ranking.md)、[机器可读结果](api-v2-nothink-ranking.json)、[口径校验](api-v2-nothink-validation.json) 与 [敏感性分析](api-v2-nothink-sensitivity.json)。这一轨道与下方历史 persona-01 实验分母、量尺、题集均不同，不可混排。

## 历史 persona-01 实验索引

下表由 `docs/run-inventory.json` 的结果元数据生成，解决通用文件名和历史目录造成的查找困难。这些文件均属于 persona-01 的早期实验与三轮稳定性素材。

文件中的 run 记录包含重试、合并和历史实验，不能解释为独立模型调用次数。不同题集、评分版本和运行轨道不可直接混排。

| 模型 | 主结果入口 | 主结果记录 | 结果文件 | 全部 run 记录 |
|---|---|---:|---:|---:|
| DeepSeek (`deepseek-v4-flash`) | [results/all-v2.json](../persona-01-linzhou/results/all-v2.json) | 252 | 30 | 2420 |
| MiniMax (`minimax-m3.1-flash`) | [results/minimax-v2/all-v2.json](../persona-01-linzhou/results/minimax-v2/all-v2.json) | 252 | 14 | 2183 |
| GLM (`glm-5.3-flash`) | [results/glm-v2/all-v2.json](../persona-01-linzhou/results/glm-v2/all-v2.json) | 252 | 11 | 1237 |
| 混元 Hy4 (`hy4-preview`) | [results/hy4-v2/results-v2-full-hy4b.json](../persona-01-linzhou/results/hy4-v2/results-v2-full-hy4b.json) | 252 | 9 | 1336 |
| MiMo (`mimo-v2.6-flash`) | [results/rep1-mimo.json](../persona-01-linzhou/results/rep1-mimo.json) | 252 | 4 | 768 |
| GPT 运行时 (`gpt-6.1-sol`) | [results/gpt-runtime/r1.json](../persona-01-linzhou/results/gpt-runtime/r1.json) | 252 | 3 | 756 |

## 查找说明

- DeepSeek：主结果文件名不含模型名；按 meta.model 识别。
- MiniMax：另保留 rep 前缀的重复实验和重试记录。
- GLM：包含分段、重试、条件级合并及已保存的抽样 trace 分析。
- 混元 Hy4：三轮稳定性使用 hy4-v2 下首轮及 rep2、rep3 的共同有效样本。
- MiMo：三轮结果使用根 results 下的 rep1-mimo、rep2-mimo、rep3-mimo。
- GPT 运行时：独立运行时轨道；冻结输入、逐条回复及三轮汇总另见 gpt-runtime。

每个结果文件的运行数与源 SHA-256 见机器可读索引 [model-results.json](model-results.json)；全部结果（包括无模型元数据的冻结输入和分析文件）仍以 [run-inventory.json](run-inventory.json) 为准。
