# product-cases

产品级白盒评审层。方法说明见 [../docs/product-review.md](../docs/product-review.md)。

这一层不跑模型。它提供的是可让人扮演对方、按统一判定打分的用例与题目，用来回答模型跑分回答不了的问题：这件事值不值得做，做出来是否得体。

```text
product-cases/
├── data/
│   ├── cases.json              3026 条用例（1930 条已评审，1096 条待评审）
│   ├── questions.json          392 道测试题（245 道完整规格）
│   ├── role-cards.json         2 张可执行角色卡
│   ├── taxonomy.json           11 个一级领域 + 97 个二级领域
│   ├── segments.json           36 类目标人群
│   ├── need-units.json         152 个需求单元（人群 × 价值领域）
│   ├── value-goals.json        42 个价值目标
│   ├── capabilities.json       61 条基础能力与身份等级
│   ├── review-rules.json       22 条评审规则
│   ├── scoring-rules.json      13 条打分规则
│   ├── refusal-matrix.json     拒绝强度 × 目标必要性 9 格
│   └── counterpart-scale.json  对方体验量表 5 个维度
├── schema/
│   ├── case.schema.json
│   ├── question.schema.json
│   └── role-card.schema.json
├── persona-links.json          10 个人物到用例的映射
└── validate_cases.py
```

## 校验

```bash
python3 product-cases/validate_cases.py
```

## 几个容易误读的地方

`curation` 为 `raw` 的 1096 条用例只登记了任务与所需能力，没有标题与适配判断，不能直接用于评审。统计口径上它们是候选池，不是题集。

`spec_completeness` 为 `完整规格` 的 245 道题才可以直接开跑：对方设定与隐藏信息内嵌在题面里。另外 147 道标为 `待补角色卡`，只有一句话任务与达成判定，缺对方设定。单独成表的角色卡只有 2 张，是额外写到底线与披露触发条件的加强版。

`question_ids` 为空表示该用例还没有出题。3026 条用例里只有 392 条有题。

数据中的成功判定只填了「达成」，「得体止步」与「失败」两档为空，是已知缺口，详见方法文档第 10 节。

## 重新生成

数据由原始导出经 `tools/product-cases/import_whitebox.py` 生成，人物映射由 `tools/product-cases/build_persona_links.py` 生成。原始导出不随仓库分发。
