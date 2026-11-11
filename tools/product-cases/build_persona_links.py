#!/usr/bin/env python3
"""Build `product-cases/persona-links.json`.

The two evaluation tracks in this repository answer different questions:

* `persona-*` scores a model on memory, goal tracking and restraint inside a
  single synthetic life;
* `product-cases` scores whether a case is worth building and whether the
  agent behaves acceptably towards the counterpart.

The link file connects them: for each persona it names a small set of cases
drawn from that persona's own life, so the same individual carries evidence
on both tracks. The selection and the domain assignment are editorial and
hand-checked; this script only validates them against the shipped data.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "product-cases" / "data"

SELECTION = [
    {
        "persona": "persona-01-linzhou",
        "name": "林舟",
        "role": "互联网公司内容运营，杭州，租住一居室",
        "cases": [
            ("AU-34", "WORK.MARKETING",
             "选题并发布笔记是她的本职工作，属于只出建议、不对外代发的一档。"),
            ("P1-市场-06", "HOME.RESIDENCE",
             "角色卡里房东报价 4500、底线 4100，与她的月租一致；结果与对方体验可同时验证。"),
            ("P7-共享-08", "REL.BOND",
             "和催婚的妈妈吵架后发一条微信，对应她与母亲高频联系又常拌嘴的那条线。"),
        ],
    },
    {
        "persona": "persona-02-xutang",
        "name": "许棠",
        "role": "成都独立插画师",
        "cases": [
            ("P7-公众-07", "ADMIN.RIGHTS",
             "被第三次指控抄袭时要求对方撤回，是独立创作者最需要留证的一类冲突。"),
            ("M4-01", "FIN.RECEIVABLE",
             "客户拖欠包装设计费，属于自由职业者最典型的应收款场景。"),
            ("M5-03", "WORK.CLIENT",
             "只退截图对应的工时、不退整笔，守住工作量边界又要保住评价。"),
        ],
    },
    {
        "persona": "persona-03-chenyu",
        "name": "陈屿",
        "role": "武汉硬件工程师",
        "cases": [
            ("P6-市场-02", "WORK.RESOURCE",
             "从供应商锁住原料并限制涨幅，是硬件工程师最熟的供应保障谈判。"),
            ("M2-26", "WORK.RESOURCE",
             "孔位打错后要求返工或赔偿，并另找备选工厂打样。"),
            ("M1-31", "WORK.PEOPLE",
             "远程客服兼订单助理的招聘与面试，覆盖用人一侧。"),
        ],
    },
    {
        "persona": "persona-04-suhe",
        "name": "苏禾",
        "role": "南京高中地理教师",
        "cases": [
            ("PUB-0529", "LEARN.COURSE",
             "按课文、词汇表和学生水平生成课件，是备课的日常交付。"),
            ("PUB-0098", "LEARN.SCHOOL",
             "按成绩和评估记录写期末评语，涉及对家长的表达分寸。"),
            ("P4-机构-03", "REL.SOCIAL",
             "教师节祝福要写得不像模板，是礼仪类表达而不是任务达成。"),
        ],
    },
    {
        "persona": "persona-05-zhengbei",
        "name": "郑北",
        "role": "西安独立播客主播",
        "cases": [
            ("P4-公众-05", "INTEREST.EXPRESSION",
             "下播后给常驻听众逐条发感谢，考验一对多的分身乏术。"),
            ("P6-公众-11", "INTEREST.EXPRESSION",
             "把愿望单在两个月内做起来，是创作者增长目标的最短路径。"),
            ("PUB-0873", "WORK.RESEARCH",
             "调研大会嘉宾并归纳主题，用于选题和邀约。"),
        ],
    },
    {
        "persona": "persona-06-linlan",
        "name": "林澜",
        "role": "厦门社区咖啡店店主",
        "cases": [
            ("P4-市场-02", "WORK.COMMERCIAL",
             "用一条微信把半年没来的老客请回店里，是社区小店最看重的一招。"),
            ("P7-公众-10", "WORK.CLIENT",
             "盯住多个平台的职业差评，来一条处理一条，直接决定门店评分。"),
            ("P6-公众-08", "ADMIN.RIGHTS",
             "澄清平台上说店里用过期食材的谣言，涉及举证和公开表述。"),
        ],
    },
    {
        "persona": "persona-07-zhouheng",
        "name": "周衡",
        "role": "青岛海洋科研助理",
        "cases": [
            ("P5-共享-05", "REL.BOND",
             "把实验失败讲给妈妈听，是科研阶段最常见的情绪支持需求。"),
            ("PUB-0354", "WORK.RESEARCH",
             "只引用用户上传的文献起草综述，考验来源约束的遵守。"),
            ("PUB-0343", "WORK.RESEARCH",
             "检索文献并列出候选材料及依据。"),
        ],
    },
    {
        "persona": "persona-08-tangning",
        "name": "唐宁",
        "role": "苏州非遗策展协调员",
        "cases": [
            ("P2-公众-11", "WORK.COMMERCIAL",
             "让营销见面会每场稳定到场，是策展招商的硬指标。"),
            ("P2-公众-09", "REL.COMMUNITY",
             "办成一场异地读书会，覆盖场地、报名和到场确认。"),
            ("P3-公众-07", "REL.COMMUNITY",
             "找到能一起张罗活动的长期伙伴，属于连接而非单次协调。"),
        ],
    },
    {
        "persona": "persona-09-luochen",
        "name": "罗晨",
        "role": "重庆越野跑教练",
        "cases": [
            ("PUB-0018", "HEALTH.FITNESS",
             "把配速、心率、血压变化写成简报，是教练看数据的日常。"),
            ("PUB-0639", "HEALTH.FITNESS",
             "把马拉松目标拆成训练计划并排进日程，覆盖长程目标推进。"),
            ("P2-公众-05", "REL.COMMUNITY",
             "凑齐一场周末活动的人数，是他带学员之外的组织能力。"),
        ],
    },
    {
        "persona": "persona-10-guyao",
        "name": "顾遥",
        "role": "北京纪录片剪辑师",
        "cases": [
            ("P4-公众-09", "INTEREST.EXPRESSION",
             "得体回复频道第一条差评，考验公开回应时的情绪与分寸。"),
            ("M5-03", "WORK.CLIENT",
             "只退截图对应的工时、不退整笔，守住工作量边界又保住评价。"),
            ("P7-对等-09", "REL.SOCIAL",
             "拒绝同事再一次把活推过来又不撕破脸。"),
        ],
    },
]


def main() -> int:
    cases = {c["case_id"]: c for c in json.loads((DATA / "cases.json").read_text(encoding="utf-8"))}
    questions = json.loads((DATA / "questions.json").read_text(encoding="utf-8"))
    role_cards = {r["role_card_id"] for r in json.loads((DATA / "role-cards.json").read_text(encoding="utf-8"))}
    taxonomy = json.loads((DATA / "taxonomy.json").read_text(encoding="utf-8"))
    domains = {e["code"] for e in taxonomy["level2"]}
    questions_by_case = {}
    for q in questions:
        questions_by_case.setdefault(q.get("case_id"), []).append(q["question_id"])

    out = []
    errors = []
    for entry in SELECTION:
        linked = []
        for case_id, domain, why in entry["cases"]:
            if case_id not in cases:
                errors.append(f"{entry['persona']}: unknown case {case_id}")
                continue
            if domain not in domains:
                errors.append(f"{entry['persona']}: unknown domain {domain}")
                continue
            case = cases[case_id]
            linked.append(
                {
                    "case_id": case_id,
                    "title": case.get("title") or case.get("task"),
                    "level": case.get("level"),
                    "social_tier": case.get("social_tier"),
                    "domain_code": domain,
                    "role_card": case_id if case_id in role_cards else None,
                    "question_ids": questions_by_case.get(case_id, []),
                    "why": why,
                }
            )
        out.append(
            {
                "persona": entry["persona"],
                "name": entry["name"],
                "role": entry["role"],
                "cases": linked,
            }
        )

    if errors:
        for error in errors:
            print("ERROR", error)
        return 1

    path = ROOT / "product-cases" / "persona-links.json"
    payload = {
        "schema": "personal-agent-benchmark-persona-links-v1",
        "note": "连接模型评测与产品评审两条轨道。用例由人工挑选并人工标注领域，不是自动匹配结果。",
        "personas": out,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    total = sum(len(p["cases"]) for p in out)
    print(f"wrote {path.relative_to(ROOT)}: {len(out)} personas, {total} linked cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
