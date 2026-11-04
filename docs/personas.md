# 十个人物题库

## 范围与状态

仓库现包含 persona-01～10。所有人物、对话、项目、地址、订单号和健康信息均为合成数据，不对应真实个人或业务记录。

persona-01 保留原有题目、历史模型结果和统计，不用新数据覆盖。persona-02～10 是本轮新增题库，先完成结构、反泄漏、规则自洽和 fixture dry-run 校验，随后与 persona-01 一同完成五家 API 模型的单轮正式评测（api-v2-nothink）。dry-run 只验证链路，不代表模型能力；本轮通过率与统一排名见 docs/api-v2-nothink-ranking.md。十个人物均为合成数据，评测为单轮结果，不是通用模型能力榜单。

| 人物 | 合成角色 | 数据入口 | 当前状态 |
|---|---|---|---|
| persona-01 林舟 | 原有人物 | [题库](../persona-01-linzhou/data/persona-01.json) | 63题；保留历史模型结果；本轮五家API单轮评测 |
| persona-02 许棠 | 成都独立插画师 | [profile](../persona-02-xutang/profile.md)、[题库](../persona-02-xutang/data/persona-02.json) | 63题；fixture dry-run通过；本轮五家API单轮评测 |
| persona-03 陈屿 | 武汉硬件工程师 | [profile](../persona-03-chenyu/profile.md)、[题库](../persona-03-chenyu/data/persona-03.json) | 63题；fixture dry-run通过；本轮五家API单轮评测 |
| persona-04 苏禾 | 南京高中地理教师 | [profile](../persona-04-suhe/profile.md)、[题库](../persona-04-suhe/data/persona-04.json) | 63题；fixture dry-run通过；本轮五家API单轮评测 |
| persona-05 郑北 | 西安独立播客主播 | [profile](../persona-05-zhengbei/profile.md)、[题库](../persona-05-zhengbei/data/persona-05.json) | 63题；fixture dry-run通过；本轮五家API单轮评测 |
| persona-06 林澜 | 厦门社区咖啡店店主 | [profile](../persona-06-linlan/profile.md)、[题库](../persona-06-linlan/data/persona-06.json) | 63题；fixture dry-run通过；本轮五家API单轮评测 |
| persona-07 周衡 | 青岛海洋科研助理 | [profile](../persona-07-zhouheng/profile.md)、[题库](../persona-07-zhouheng/data/persona-07.json) | 63题；fixture dry-run通过；本轮五家API单轮评测 |
| persona-08 唐宁 | 苏州非遗策展协调员 | [profile](../persona-08-tangning/profile.md)、[题库](../persona-08-tangning/data/persona-08.json) | 63题；fixture dry-run通过；本轮五家API单轮评测 |
| persona-09 罗晨 | 重庆越野跑教练 | [profile](../persona-09-luochen/profile.md)、[题库](../persona-09-luochen/data/persona-09.json) | 63题；fixture dry-run通过；本轮五家API单轮评测 |
| persona-10 顾遥 | 北京纪录片剪辑师 | [profile](../persona-10-guyao/profile.md)、[题库](../persona-10-guyao/data/persona-10.json) | 63题；fixture dry-run通过；本轮五家API单轮评测 |

## 新人物的统一规格

每个新人物包含：

- 23个session，ID固定为S01～S23，按时间顺序排列；
- 63个检查点，ID固定为CP01～CP63；
- 7个维度各9题：D1记忆、D2目标推进、D3克制与授权、D4表达、D5界面、D6时间、D7工具；
- 160条可执行评分规则，以及每题一份用于反验规则的fixture；
- 独立的检索记忆和结果目录，不与其他人物共享运行状态；
- 四条件各63条，完整一轮为252条fixture运行。

63类场景在各人物间保持一致，用于保证覆盖可比；事实、项目、时间线、期望答案和工具参数独立构造，并加入不改变评分目标的表达变体。它们是扩展题集，不是10次独立重复采样，也不能据此计算模型显著性。

## 文件结构

以persona-02为例：

```text
persona-02-xutang/
├── profile.md
├── data/
│   ├── persona-02.json       人物、埋点、检查点和期望行为
│   ├── sessions.json         实际进入上下文组装的合成对话
│   ├── assertions.json      触发轮次、证据session和评分规则
│   └── dry_run_replies.json 标准fixture，不是模型回复
└── results/
    └── dry-run.json          252条fixture链路结果
```

`dry-run.json` 只证明运行器、四条件、回复协议和评分链路可执行。fixture被统一喂给各条件，不能将其分数解释为模型表现，也不能用来判断C0是否优于或弱于C3。

## 校验口径

`docs/persona-validation.json` 记录机器可读结果。当前校验覆盖：

1. 9个新人物、207个session、567个检查点、1440条规则；
2. 567份fixture全部通过各自规则，排除无解词表和工具参数矛盾；
3. 2268个上下文输入的触发轮次、证据时序、C0/C1边界和canary扫描；
4. 2268条dry-run的唯一 `(cp, condition)`、回复schema、矩阵完整性和人物隔离；
5. 人物间完全相同的触发话术数量，作为表面多样性信号而非质量分数。

校验不包括完整语义人工评审，也不证明规则能覆盖所有好答案。固定词表和结构断言仍是弱代理。当前运行器是prompt级隔离，不是独立权限沙盒。

## 复现

```bash
python3 tools/personas/build_expansion.py
python3 tools/personas/validate_bundle.py

# 单人物完整fixture运行，不访问模型服务
python3 persona-01-linzhou/runner/runner.py \
  --persona-root persona-02-xutang \
  --dry-run --out dry-run.json

# 所有新人物数据及已有dry-run结果校验
python3 tools/personas/validate_bundle.py --require-dry-run
```

本轮已完成五家 API 模型的单轮正式评测，结果见 docs/api-v2-nothink-ranking.md。若要追加轮次、模型或复跑，仍需另行明确范围与预算，并自行配置服务凭据。不要把凭据写入人物数据或提交到 Git。
