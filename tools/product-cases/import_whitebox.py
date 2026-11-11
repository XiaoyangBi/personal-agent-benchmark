#!/usr/bin/env python3
"""Normalise the white-box case export into the product-cases data layer.

The importer reads two operator-supplied exports that are not redistributed
in this repository:

* a Feishu Base snapshot (``.base``) holding the case library, the test
  question grid, the role cards, the segment list and the review rules;
* an ``.xlsx`` workbook holding the two-level domain taxonomy.

Keeping the transform in the repository makes the shipped data auditable and
re-runnable against a fresh export:

    python3 tools/product-cases/import_whitebox.py \
        --base /path/to/whitebox.base \
        --taxonomy /path/to/domain-taxonomy.xlsx \
        --out product-cases/data

What is dropped, and why, is documented in ``docs/product-review.md``:
verbatim end-user quotes, external links, platform handles, contact records,
reviewer names and internal product names never reach the output.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import json
import math
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
import xml.etree.ElementTree as ET

MAIN_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

TABLE_KEYS = {
    "tblXLFe53tx32i2o": "cases",
    "tbltDLRR2266Sngy": "questions",
    "tblKh1sW7O0VcbBo": "role_cards",
    "tbl1OXMXDjT0ZMw6": "need_units",
    "tblIG3Aay3PvCSw2": "segments",
    "tblw3TJZdISVcmeE": "value_goals",
    "tblyGrmZgmsHyFYt": "capabilities",
    "tblADk8LPg8fpbTx": "review_rules",
    "tblUJNkFwp4Q9fRo": "scoring_rules",
    "tblehRg96KbplTLb": "refusal_matrix",
    "tblgsAeTfCTeLTLL": "counterpart_scale",
}


# ------------------------------------------------------------------ base read

def read_base(path: Path) -> dict:
    outer = json.loads(path.read_text(encoding="utf-8"))
    snapshots = json.loads(gzip.decompress(base64.b64decode(outer["gzipSnapshot"])))
    tables = {}
    for snapshot in snapshots:
        data = snapshot["schema"]["data"]
        meta = data["table"]["meta"]
        key = TABLE_KEYS.get(meta["id"])
        if key is None:
            continue
        tables[key] = {
            "name": meta["name"],
            "fields": data["table"].get("fieldMap") or {},
            "records": data.get("recordMap") or {},
        }
    missing = sorted(set(TABLE_KEYS.values()) - set(tables))
    if missing:
        raise SystemExit(f"missing tables in export: {missing}")
    return tables


def normalise(field: dict, raw):
    if raw is None:
        return None
    value = raw.get("value") if isinstance(raw, dict) else raw
    if value is None or value == "" or value == []:
        return None
    ftype = field.get("type")
    prop = field.get("property") or {}
    if ftype == 1:
        if isinstance(value, str):
            return value.strip() or None
        if isinstance(value, list):
            text = "".join(
                (seg.get("text") or seg.get("name") or "") if isinstance(seg, dict) else str(seg)
                for seg in value
            ).strip()
            return text or None
        return str(value)
    if ftype == 2:
        return value
    if ftype == 3:
        return next((o.get("name") for o in prop.get("options") or [] if o.get("id") == value), value)
    if ftype == 4:
        items = value if isinstance(value, list) else [value]
        return [next((o.get("name") for o in prop.get("options") or [] if o.get("id") == i), i) for i in items]
    if ftype in (18, 21):
        return list(value) if isinstance(value, list) else [value]
    return value


def rows(table: dict) -> list[dict]:
    index = {field.get("name"): fid for fid, field in table["fields"].items() if field.get("name")}
    out = []
    for record_id, record in table["records"].items():
        row = {"__record_id__": record_id}
        for name, fid in index.items():
            row[name] = normalise(table["fields"][fid], record.get(fid))
        out.append(row)
    return out


# -------------------------------------------------------------- xlsx reading

def col_index(ref: str) -> int:
    letters = re.match(r"([A-Z]+)", ref).group(1)
    total = 0
    for ch in letters:
        total = total * 26 + (ord(ch) - 64)
    return total - 1


def read_sheet(path: Path, sheet_index: int) -> list[list[str]]:
    with zipfile.ZipFile(path) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall(f"{MAIN_NS}si"):
                shared.append("".join(node.text or "" for node in item.iter(f"{MAIN_NS}t")))
        root = ET.fromstring(archive.read(f"xl/worksheets/sheet{sheet_index}.xml"))
        grid = []
        for row in root.iter(f"{MAIN_NS}row"):
            cells = {}
            for cell in row.iter(f"{MAIN_NS}c"):
                kind = cell.get("t")
                value_node = cell.find(f"{MAIN_NS}v")
                inline = cell.find(f"{MAIN_NS}is")
                if kind == "s" and value_node is not None:
                    text = shared[int(value_node.text)]
                elif kind == "inlineStr" and inline is not None:
                    text = "".join(node.text or "" for node in inline.iter(f"{MAIN_NS}t"))
                elif value_node is not None:
                    text = value_node.text or ""
                else:
                    text = ""
                cells[col_index(cell.get("r"))] = text.strip()
            width = max(cells) + 1 if cells else 0
            grid.append([cells.get(i, "") for i in range(width)])
        return grid


def read_taxonomy(path: Path) -> dict:
    overview = read_sheet(path, 1)
    detail = read_sheet(path, 2)
    header_at = next(i for i, row in enumerate(detail) if row and row[0] == "一级领域")
    header = detail[header_at]
    level2 = []
    for row in detail[header_at + 1:]:
        if len(row) < 4 or not row[1].strip():
            continue
        level2.append({header[i]: (row[i] if i < len(row) else "") for i in range(len(header))})
    level1 = []
    for row in overview:
        if len(row) >= 4 and re.fullmatch(r"[A-Z]{3,8}", row[0].strip()):
            level1.append(
                {
                    "code": row[0].strip(),
                    "name": row[1].strip(),
                    "definition": row[2].strip(),
                    "level2_count": int(row[3]) if row[3].strip().isdigit() else None,
                }
            )
    return {"level1": level1, "level2": level2}


# ------------------------------------------------------------- sanitisation

SOURCE_TYPE_MAP = {
    "公开用例（agentusecases.ai）": "public-case-library",
    "小艺白盒": "internal-whitebox",
    "谢扬": "internal-contributor-a",
    "诗洋": "internal-contributor-b",
    "商家需求调研": "merchant-interview",
    "赚钱需求调研": "monetisation-interview",
    "合并任务表 v3": "merged-task-table",
}

SCRUB = [
    # reviewer and staff names, including the pinyin forms used in free text
    (re.compile(r"[（(][^）)]*(?:谢扬|马小艺|诗洋|志建|许凡|Yafei|Fan Xu|芃芃|小艺|Zhijian)[^）)]*[）)]"), ""),
    (re.compile(r"(?:Zhijian|Yafei|Fan Xu)\s*原写"), ""),
    (re.compile(r"(?:谢扬|马小艺|诗洋|志建|许凡|Yafei|Fan Xu|芃芃|小艺|Zhijian)"), "评审参与者"),
    # internal product names
    (re.compile(r"Eazo"), "被测产品"),
    (re.compile(r"Instinct"), "某垂直场景产品"),
    (re.compile(r"Fellou"), "某 agent 产品"),
    # internal documents and any external link
    (re.compile(r"reports/[^\s，。；）)]+"), ""),
    (re.compile(r"https?://\S+"), ""),
    (re.compile(r"\d{4}-\d{2}-\d{2}\s*(?:会议|产品会|市场日会|群聊)?"), "评审记录"),
    (re.compile(r"[（(]\s*[，,]\s*"), "（"),
    (re.compile(r"[ \t]{2,}"), " "),
]

# Segment descriptions are rewritten from the operator's notes so that no
# named individual or vendor survives into the published data.
SEGMENT_PROFILES = {
    "创业公司创始人（非 AI）": "非 AI 背景的技术型创始人，手里有医院表单、保险预审和租约续签要处理；技术能力强，但要求所有对外动作由本人复核后才发出。",
    "自由职业者": "自由职业的网站开发者，希望 agent 自动找到客户并卖出建站服务；会给 agent 一个代码仓库当工作底稿，并接入任务看板。",
    "房产经纪人": "靠房源网站获客的经纪人，想自动跟进线上线索；房源文案坚持自己写，技术熟练度一般，只用现成工具。",
    "小生意老板": "小型承包商的老板，办公室文书堆积；愿意把办许可、约检查、通知保险公司这类事务整体交出去，但要看到回执。",
    "电商卖家": "收购并运营电商品牌的经营者，不是开发者；希望尽量自动化选品、上架和客服，对批量操作的授权比较谨慎。",
    "AI 公司创始人": "独自经营 SaaS 的创始人，没有销售团队；把客户画像、日历和邮箱交给 agent 做全流程外联，只抽查前若干封邮件。",
    "内容创作者": "写作者或内容创作者，邮件和会议邀约多；希望 agent 定时扫邮箱、起草回复并把邀约加进日历。",
    "开发者": "日常网购的开发者，每周购物清单八成重复；自己写过命令行工具和编辑器插件来接管购物车，愿意用脚本换时间。",
    "自动化服务商与顾问": "做自动化交付的顾问，常替客户做测试性下单；熟悉分销和票务的后台逻辑，会用演示效果说服供应商。",
    "技术尝鲜者": "新技术尝鲜者，设备和服务订阅多；习惯把常用账户提前登录好再让 agent 操作，愿意承担尝试风险。",
    "AI 与科技从业者": "技术从业者，通讯与语音账户已配置齐全；让 agent 直接打电话订位，关注端到端是否真的办成。",
    "教师与研究者": "两位知识工作者：一位非技术背景，只想每天看最该回的几封邮件；一位政策研究者，要开发票并追踪地方立法进展。",
    "律师、会计与财务": "有税务或法务专业背景的从业者，懂流程；愿意让 agent 准备材料，但不允许它代为提交或代为承诺。",
    "销售": "同时推进多笔交易和租约的销售，邮箱和日历接入 agent；所有对外内容必须本人过一遍。",
    "产品经理": "大厂产品经理，技术熟悉度高，自建过个人助手；想自动起草邮件、查票价，对助手的行为边界很敏感。",
    "招聘与 HR": "HR 负责人，手里有大量历史卡片要归档；用付费编码助手批量处理，关注批量操作的可回滚性。",
    "市场营销人员": "度假租赁行业的市场从业者，常在直播里演示工具；需要 agent 规划跨城行程并给出可比价方案。",
    "企业运营与客服": "管理数百套房的物业经理，团队已开始用浏览器内助手；会自建数据库，关注多人协作时的权限边界。",
    "投资分析与投资人": "投资机构分析师，习惯自己核数；让 agent 先搜一遍是否有属于自己的无主资金并填好材料，最后一步自己提交。",
    "消费维权者": "被航司取消航班的旅客，网站改签失败、退款被拒；自己研究法规后逐级申诉，需要 agent 把证据链和申诉路径整理清楚。",
    "网购与比价者": "家庭主要采购人，每周固定采购金额稳定；自己整理过常买清单，希望 agent 比价下单但不擅自替换品牌。",
    "车主与买车者": "要在本地买车的技术从业者，授权浏览器和邮箱；让 agent 同时联系多家经销商比价，成交前必须本人确认。",
    "宠物主人": "养处方粮宠物的主人，宠物保险报销材料积压数月；会用通用助手代办琐事，但医疗信息只肯给最小必要范围。",
    "家长与照护者": "有孩子的职场家长，周末要跑理发、退货、买菜、采购多件事；开启了记忆功能，希望 agent 知道自己的位置和常去门店。",
    "其他个人": "社区论坛重度用户，订阅了很多版块；平台只能逐个关闭通知，想用浏览器 agent 批量处理。",
    "求职者与学生": "正在找工作的求职者，原收入不高；让 agent 控制已登录的招聘网站批量投递，懂基本配置，但要自己决定投哪些岗位。",
    "政府事务办理者": "需要申请伤残补助的退伍军人，手里有数千页病历；不想手工翻找证据，希望 agent 先把材料索引做出来。",
    "个人理财与报税": "要打电话给税务部门办事的个人纳税人，等待时长动辄一小时；想让 agent 代等并记录要点，本人再决定怎么答。",
    "二手买卖者": "想清掉闲置物品的个人卖家，嫌挂单和回消息麻烦；在售卖期内测试过 agent 代聊，愿意全程监督。",
    "个人事务助理用户": "同时管理三个邮箱的专业人士或创业者，邮件量大；在自建网关上跑长期在线的助手，用标准邮件协议接入。",
    "就医与保险": "收到高额医院账单的患者家属；自己做过价格分析再写信谈判，需要 agent 把编码账单和保单条款对上。",
    "本地生活与预约": "即将出行的旅客，行程跨多个城市；把订票信息交给 agent 管理，关注改签和退票时的权责。",
    "房主与房东": "房屋被树枝砸穿造成水损的房主，保险公司多次拒赔；自己研究保单和州法后申诉，对理赔材料的一致性要求很高。",
    "租客": "退租时被房东扣下大部分押金的租客；会用多个助手交叉核对法律问题，并刻意重置上下文以避免被前一轮结论锚定。",
    "出行订票者": "有旅游业背景的旅客，全家出行；只在航司官网或主流比价站订票，排斥经停，偏好打字或语音交互。",
    "记者与测评者": "生活方式领域的写作者兼产品测评者，采购历史很长、会做饭；以第三方视角测试助手的实际完成度。",
}

RELATION_CODES = {"公众": "PUBLIC", "市场": "MARKET", "机构": "INSTITUTION", "对等": "PEER", "共享": "SHARED"}
PURPOSE_CODES = {
    "P1 获取": "P1_ACQUIRE",
    "P2 协调": "P2_COORDINATE",
    "P3 连接": "P3_CONNECT",
    "P4 维系": "P4_MAINTAIN",
    "P5 求助": "P5_SEEK_HELP",
    "P6 影响": "P6_INFLUENCE",
    "P7 化解": "P7_DEESCALATE",
}
LEVEL_CODES = {"L0 基础能力": "L0", "L1–L3": "L1_L3", "L4 目标驱动": "L4"}


def scrub(text):
    if not text:
        return text
    for pattern, repl in SCRUB:
        text = pattern.sub(repl, text)
    return text.strip() or None


# ------------------------------------------------------------------- writing

def clean(obj):
    """Drop empty leaves and run every remaining string through the scrubber.

    Running the scrubber at write time (rather than only on selected fields)
    means a newly added field cannot silently bypass redaction.
    """
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            if value is None or value == [] or value == {}:
                continue
            out[key] = clean(value)
        return out
    if isinstance(obj, list):
        return [clean(item) for item in obj]
    if isinstance(obj, str):
        return scrub(obj)
    return obj


def write_records(path: Path, records: list) -> int:
    lines = [json.dumps(clean(record), ensure_ascii=False) for record in records]
    path.write_text("[\n" + ",\n".join(lines) + "\n]\n", encoding="utf-8")
    return path.stat().st_size


def write_json(path: Path, payload) -> int:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path.stat().st_size


# -------------------------------------------------------------------- build

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--taxonomy", required=True, type=Path)
    parser.add_argument("--out", default=Path("product-cases/data"), type=Path)
    args = parser.parse_args()

    tables = read_base(args.base)
    taxonomy = read_taxonomy(args.taxonomy)

    case_rows = rows(tables["cases"])
    case_label = {r["__record_id__"]: r.get("用例ID") for r in case_rows if r.get("用例ID")}


    # ---- lookup tables -----------------------------------------------------
    segments = rows(tables["segments"])
    seg_label = {r["__record_id__"]: r.get("人群名称") for r in segments}
    seg_of_label = {r.get("人群名称"): r["__record_id__"] for r in segments}

    capabilities = rows(tables["capabilities"])
    cap_label = {}
    for r in capabilities:
        code = r.get("编号")
        action = r.get("动作")
        cap_label[r["__record_id__"]] = f"{code} {action}".strip() if code else action

    need_units = rows(tables["need_units"])
    nu_label = {r["__record_id__"]: r.get("需求单元") for r in need_units}

    value_goals = rows(tables["value_goals"])
    vg_label = {
        r["__record_id__"]: " / ".join(x for x in [r.get("价值一级"), r.get("价值二级")] if x)
        for r in value_goals
    }

    questions = rows(tables["questions"])
    q_label = {r["__record_id__"]: r.get("测试题ID") for r in questions}

    role_cards = rows(tables["role_cards"])
    rc_label = {r["__record_id__"]: r.get("编号") for r in role_cards}

    # ---- questions ---------------------------------------------------------
    question_out = []
    questions_of_case = defaultdict(list)
    for r in questions:
        qid = r.get("测试题ID")
        if not qid:
            continue
        case_ref = r.get("所属用例") or []
        case_ids = [case_label[c] for c in case_ref if c in case_label]
        for cid in case_ids:
            questions_of_case[cid].append(qid)
        knob = r.get("旋钮")
        if isinstance(knob, str):
            try:
                knob = json.loads(knob)
            except json.JSONDecodeError:
                knob = {"raw": knob}
        question_out.append(
            {
                "question_id": qid,
                "set": r.get("集合"),
                "purpose": PURPOSE_CODES.get(r.get("目的"), r.get("目的")),
                "relation": RELATION_CODES.get(r.get("关系"), r.get("关系")),
                "difficulty": r.get("难度"),
                "task_type": r.get("任务类型"),
                "spec_completeness": r.get("规格完整度"),
                "case_id": case_ids[0] if len(case_ids) == 1 else case_ids or None,
                "segment": next((seg_label[s] for s in (r.get("所属人群") or []) if s in seg_label), None),
                "value_area": r.get("价值一级"),
                "task": scrub(r.get("一句话任务")),
                "user_preconditions": r.get("用户侧前置"),
                "counterpart_setting": scrub(r.get("对方设定")),
                "counterpart_hidden": scrub(r.get("对方隐藏信息")),
                "disclosure_condition": scrub(r.get("披露条件")),
                "midway_event": scrub(r.get("中途事件")),
                "checkpoints": scrub(r.get("确认点")),
                "veto": scrub(r.get("一票否决")),
                "constraints": scrub(r.get("约束")),
                "knobs": knob,
                "verdict_reached": scrub(r.get("成功判定·达成")),
                "verdict_stopped": scrub(r.get("成功判定·得体止步")),
                "verdict_failed": scrub(r.get("成功判定·失败")),
                "scoring_notes": scrub(r.get("评分要点")),
                "medium": r.get("媒介"),
                "authorization_scope": r.get("授权范围"),
                "offline_part": scrub(r.get("线上部分")),
                "may_build_app": r.get("可能需要生成应用"),
                "half_set": r.get("半程测试集"),
                "role_card": next((rc_label[x] for x in (r.get("对方角色卡") or []) if x in rc_label), None),
            }
        )

    # ---- cases -------------------------------------------------------------
    case_out = []
    for r in case_rows:
        cid = r.get("用例ID")
        if not cid:
            continue
        scores = {
            "v1": r.get("V1分"), "v2": r.get("V2分"), "v3": r.get("V3分"),
            "v4": r.get("V4分"), "v5": r.get("V5分"),
            "context": r.get("Context分"), "memory": r.get("记忆分"),
            "long_horizon": r.get("长程分"), "verifiable": r.get("可验证分"),
            "metric_fit": r.get("指标贴合分"), "goal_alignment": r.get("目标对齐分"),
            "market_impact": r.get("市场冲击分"), "need_composite": r.get("需求综合分"),
            "feasibility": r.get("实现系数"),
        }
        case_out.append(
            {
                "case_id": cid,
                "curation": "curated" if r.get("标题") else "raw",
                "title": r.get("标题"),
                "task": r.get("一句话任务"),
                "level": LEVEL_CODES.get(r.get("层级"), r.get("层级")),
                "social_tier": r.get("社交档"),
                "identity_mode": r.get("身份方式"),
                "counterpart": r.get("对方是谁"),
                "scenario_bucket": r.get("高优场景"),
                "success_criteria": scrub(r.get("成功标准")),
                "stop_points": scrub(r.get("停止点")),
                "reference_steps": scrub(r.get("参考步骤")),
                "capabilities": [cap_label[c] for c in (r.get("需要的能力") or []) if c in cap_label],
                "authorization": r.get("授权等级"),
                "card_type": r.get("交卡类型"),
                "card_boundary": {"是": True, "否": False}.get(r.get("交卡边界")),
                "card_reason": scrub(r.get("交卡理由")),
                "tools": scrub(r.get("使用的工具")),
                "tool_channel": scrub(r.get("工具通道")),
                "trigger": r.get("触发原因"),
                "frequency": r.get("预估频率"),
                "user_minutes": r.get("用户投入分钟"),
                "loss_ceiling": r.get("失败损失上限"),
                "result_value": scrub(r.get("结果价值")),
                "fit": r.get("适合度"),
                "fit_reason": scrub(r.get("适合理由")),
                "highlight": scrub(r.get("选题亮点")),
                "profile_source": r.get("画像来源"),
                "solution_source": r.get("解法来源"),
                "learning_track": r.get("学习清单"),
                "source_type": SOURCE_TYPE_MAP.get(r.get("来源类型"), r.get("来源类型")),
                "segment": next((seg_label[s] for s in (r.get("所属人群") or []) if s in seg_label), None),
                "need_unit": next((nu_label[s] for s in (r.get("所属需求") or []) if s in nu_label), None),
                "value_goal": next((vg_label[s] for s in (r.get("所属价值目标") or []) if s in vg_label), None),
                "question_ids": questions_of_case.get(cid) or [],
                "scores": {k: v for k, v in scores.items() if v is not None},
            }
        )
    case_out.sort(key=lambda c: c["case_id"])

    # ---- role cards --------------------------------------------------------
    role_out = []
    for r in role_cards:
        role_out.append(
            {
                "role_card_id": r.get("编号"),
                "role": r.get("角色"),
                "identity_and_relation": scrub(r.get("身份和关系")),
                "public_stance": scrub(r.get("公开立场")),
                "goals_and_bottom_line": scrub(r.get("目标和底线")),
                "hidden_information": scrub(r.get("隐藏信息和披露条件")),
                "refusal_intensity": scrub(r.get("拒绝强度")),
                "emotion_threshold": scrub(r.get("情绪阈值和结束条件")),
                "speaking_style": scrub(r.get("说话风格")),
                "reaction_to_ai": scrub(r.get("知道对方是 AI 后的反应")),
                "play_rules": scrub(r.get("给扮演方的规则")),
            }
        )

    # ---- segments ----------------------------------------------------------
    seg_out = []
    for r in segments:
        name = r.get("人群名称")
        if not name:
            continue
        seg_out.append(
            {
                "segment": name,
                "group": r.get("人群大类"),
                "profile": SEGMENT_PROFILES.get(name),
                "need_unit_count": r.get("需求单元数"),
                "case_count": r.get("用例数"),
            }
        )

    # ---- need units --------------------------------------------------------
    nu_out = []
    for r in need_units:
        nu_out.append(
            {
                "need_unit": r.get("需求单元"),
                "segment": next((seg_label[s] for s in (r.get("所属人群") or []) if s in seg_label), None),
                "value_area": r.get("价值一级"),
                "value_tier": r.get("价值档"),
                "frequency_tier": r.get("频率档"),
                "cost_tier": r.get("成本档"),
                "loss_tier": r.get("失败损失档"),
                "user_effort_tier": r.get("用户投入档"),
                "authorization_tier": r.get("授权等级档"),
                "composite": r.get("综合分"),
                "feasibility": r.get("可实现系数"),
                "confidence": r.get("置信度"),
                "confidence_score": r.get("置信分"),
                "quadrant": r.get("象限"),
                "priority_list": r.get("优先清单"),
                "evidence_type": r.get("证据类型"),
                "value_basis": scrub(r.get("价值依据")),
                "frequency_basis": scrub(r.get("频率依据")),
                "interview_calibrated": r.get("是否经访谈校准"),
                "external_ratio": r.get("对外交互占比"),
                "case_count": r.get("用例数"),
                "feasible_case_ratio": r.get("可实现用例占比"),
            }
        )

    # ---- value goals -------------------------------------------------------
    vg_out = []
    for r in value_goals:
        vg_out.append(
            {
                "value_area": r.get("价值一级"),
                "value_goal": r.get("价值二级"),
                "definition": r.get("定义"),
                "case_count": r.get("用例数"),
            }
        )

    # ---- capabilities ------------------------------------------------------
    cap_out = []
    for r in capabilities:
        if not r.get("编号"):
            continue
        cap_out.append(
            {
                "capability_id": r.get("编号"),
                "action": r.get("动作"),
                "medium": r.get("媒介"),
                "can_do_criterion": r.get("判定为“能”的标准"),
                "own_identity_level": r.get("自有身份等级"),
                "takeover_identity_level": r.get("接管用户等级"),
                "preconditions": scrub(r.get("前置条件")),
            }
        )

    # ---- rules -------------------------------------------------------------
    review_out = []
    seen = set()
    for r in rows(tables["review_rules"]):
        name = r.get("规则")
        if not name or name in seen:
            continue
        seen.add(name)
        review_out.append(
            {
                "rule": name,
                "statement": scrub(r.get("怎么做")),
                "rationale": scrub(r.get("为什么")),
            }
        )

    scoring_out = []
    for r in rows(tables["scoring_rules"]):
        name = r.get("规则")
        if not name:
            continue
        scoring_out.append({"rule": name, "definition": scrub(r.get("内容"))})

    refusal_out = []
    for r in rows(tables["refusal_matrix"]):
        refusal_out.append(
            {
                "refusal_intensity": r.get("拒绝强度"),
                "goal_necessity": r.get("目标必要性"),
                "counterpart_says": r.get("对方的典型说法"),
                "expected_action": r.get("agent 应该怎么做"),
                "penalty": r.get("没做到时怎么计分"),
            }
        )

    scale_out = []
    for r in rows(tables["counterpart_scale"]):
        scale_out.append(
            {
                "dimension": r.get("维度"),
                "what_to_watch": r.get("看什么"),
                "score_1": r.get("1 分"),
                "score_3": r.get("3 分"),
                "score_5": r.get("5 分"),
            }
        )

    # ---- taxonomy ----------------------------------------------------------
    taxonomy_out = {
        "schema": "personal-agent-benchmark-domain-taxonomy-v1",
        "axes": {
            "domain": "生活领域，两级：11 个一级领域、97 个二级领域。",
            "relation": "对方是谁。公众 / 市场 / 机构 / 对等 / 共享。",
            "purpose": "要达成什么。P1 获取 / P2 协调 / P3 连接 / P4 维系 / P5 求助 / P6 影响 / P7 化解。",
            "level": "需要的能力层级。L0 基础能力 / L1–L3 单点社交 / L4 目标驱动。",
            "task_type": "即时任务 / 长程任务 / 监控任务。",
        },
        "relations": [{"code": v, "name": k} for k, v in RELATION_CODES.items()],
        "purposes": [{"code": v, "name": k} for k, v in PURPOSE_CODES.items()],
        "levels": [
            {"code": "L0", "name": "L0 基础能力", "definition": "只和信息工具或系统打交道，不涉及对外沟通，用来守住基础能力下限。"},
            {"code": "L1_L3", "name": "L1–L3", "definition": "目标单一、对方明确，靠一次或少数几轮对外沟通完成。"},
            {"code": "L4", "name": "L4 目标驱动", "definition": "目标需要跨渠道、跨多轮推进，agent 要自己拆解并盯住结果。"},
        ],
        "level1": taxonomy["level1"],
        "level2": [
            {
                "code": entry.get("二级编码"),
                "level1_code": entry.get("一级编码"),
                "level1_name": entry.get("一级领域"),
                "name": entry.get("二级领域"),
                "definition": entry.get("领域定义"),
                "in_scope": [line for line in entry.get("纳入范围", "").split("\n") if line.strip()],
                "out_of_scope": [line for line in entry.get("排除及转归", "").split("\n") if line.strip()],
                "need_examples": [x for x in [entry.get("需求示例 1"), entry.get("需求示例 2")] if x],
            }
            for entry in taxonomy["level2"]
        ],
    }

    # ---- write -------------------------------------------------------------
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    sizes = {}
    sizes["cases.json"] = write_records(out / "cases.json", case_out)
    sizes["questions.json"] = write_records(out / "questions.json", question_out)
    sizes["role-cards.json"] = write_records(out / "role-cards.json", role_out)
    sizes["segments.json"] = write_records(out / "segments.json", seg_out)
    sizes["need-units.json"] = write_records(out / "need-units.json", nu_out)
    sizes["value-goals.json"] = write_records(out / "value-goals.json", vg_out)
    sizes["capabilities.json"] = write_records(out / "capabilities.json", cap_out)
    sizes["review-rules.json"] = write_records(out / "review-rules.json", review_out)
    sizes["scoring-rules.json"] = write_records(out / "scoring-rules.json", scoring_out)
    sizes["refusal-matrix.json"] = write_records(out / "refusal-matrix.json", refusal_out)
    sizes["counterpart-scale.json"] = write_records(out / "counterpart-scale.json", scale_out)
    sizes["taxonomy.json"] = write_json(out / "taxonomy.json", taxonomy_out)

    report = {
        "cases": len(case_out),
        "cases_curated": sum(1 for c in case_out if c["curation"] == "curated"),
        "questions": len(question_out),
        "questions_full_spec": sum(1 for q in question_out if q.get("spec_completeness") == "完整规格"),
        "role_cards": len(role_out),
        "segments": len(seg_out),
        "need_units": len(nu_out),
        "value_goals": len(vg_out),
        "capabilities": len(cap_out),
        "review_rules": len(review_out),
        "scoring_rules": len(scoring_out),
        "refusal_matrix": len(refusal_out),
        "counterpart_scale": len(scale_out),
        "domain_level1": len(taxonomy_out["level1"]),
        "domain_level2": len(taxonomy_out["level2"]),
        "bytes": sizes,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
