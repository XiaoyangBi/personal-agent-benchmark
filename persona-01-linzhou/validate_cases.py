#!/usr/bin/env python3
"""persona-01 题库一致性校验器。

三件事：
1. 结构校验（id 唯一、引用存在、字段齐全、枚举合法）
2. 剧本一致性（埋点标签与 plants 表双向对齐、关键词反泄漏）
3. 配比自检（陷阱占比、难度分布、维度分布）

用法：
    python3 validate_cases.py            # 人类可读报告
    python3 validate_cases.py --json     # 机器可读结果

退出码：0 全部通过；1 存在错误。
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "data" / "persona-01.json"

SESSIONS = [f"S{i:02d}" for i in range(1, 24)]
TIERS = {"必记", "可记", "限记-A", "限记-B", "禁记"}
DIFF_LEVELS = {"低", "中", "高", "细", "无"}
JUDGES = {"程序", "人工", "程序+人工", "多模态 judge"}
DIMS = {"D1", "D2", "D3", "D4", "D5", "D6", "D7", "综合"}
SECTION_RE = re.compile(r"^## (S\d{2})｜", re.MULTILINE)
METRIC_RE = re.compile(r"^M[1-7]\.\d{1,2}$")
TAG_RE = re.compile(r"\[((?:PB|PK|PJ)\d{2})")

errors: list[str] = []
warnings: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


def load() -> dict:
    if not DATA_FILE.exists():
        err(f"数据文件不存在：{DATA_FILE}")
        return {}
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        err(f"JSON 解析失败：{exc}")
        return {}


def check_unique(ids: list[str], label: str) -> None:
    dup = [i for i, c in Counter(ids).items() if c > 1]
    if dup:
        err(f"{label} id 重复：{sorted(dup)}")


def check_plants(plants: list[dict], cp_ids: set[str]) -> None:
    check_unique([p.get("id", "") for p in plants], "埋点")
    for p in plants:
        pid = p.get("id", "?")
        if p.get("tier") not in TIERS:
            err(f"{pid} 档位非法：{p.get('tier')}")
        if p.get("input_session") not in SESSIONS:
            err(f"{pid} input_session 非法：{p.get('input_session')}")
        for s in p.get("allowed_sessions", []):
            if s not in SESSIONS:
                err(f"{pid} allowed_sessions 含非法 session：{s}")
        if p.get("input_session") not in p.get("allowed_sessions", []):
            err(f"{pid} input_session 不在 allowed_sessions 内")
        for cp in p.get("checkpoints", []):
            if cp not in cp_ids:
                err(f"{pid} 引用了不存在的检查点：{cp}")
        if not p.get("keywords"):
            warn(f"{pid} 未配置 keywords，跳过反泄漏扫描")


def check_checkpoints(cps: list[dict], plant_ids: set[str]) -> None:
    check_unique([c.get("id", "") for c in cps], "检查点")
    for c in cps:
        cid = c.get("id", "?")
        dims = [d.strip() for d in str(c.get("dim", "")).split("/") if d.strip()]
        if not dims or any(d not in DIMS for d in dims):
            err(f"{cid} 维度非法：{c.get('dim')}")
        if c.get("session") not in SESSIONS:
            err(f"{cid} session 非法：{c.get('session')}")
        diff = c.get("difficulty", [])
        if len(diff) != 4:
            err(f"{cid} 难度参数应为 4 项，实际 {len(diff)} 项")
        for d in diff:
            if d not in DIFF_LEVELS:
                err(f"{cid} 难度档位非法：{d}")
        if c.get("judge") not in JUDGES:
            err(f"{cid} 判分方式非法：{c.get('judge')}")
        expects = c.get("expects", {})
        missing = {"text", "payload", "action"} - set(expects)
        if missing:
            err(f"{cid} expects 缺字段：{sorted(missing)}")
        if not c.get("metrics"):
            err(f"{cid} 未配置 metrics")
        for m in c.get("metrics", []):
            if not METRIC_RE.match(m):
                err(f"{cid} 指标名非法：{m}")
        if "trap" not in c:
            err(f"{cid} 缺 trap 字段")
        if "citations" not in c:
            warn(f"{cid} 缺 citations 字段，按 false 处理")


def check_distractors(items: list[dict], plant_ids: set[str]) -> None:
    check_unique([d.get("id", "") for d in items], "干扰项")
    for d in items:
        did = d.get("id", "?")
        near = d.get("near")
        if near not in plant_ids and near not in SESSIONS:
            err(f"{did} near 指向不存在的对象：{near}")
        if not (d.get("diff") or "").strip():
            err(f"{did} 未标注与目标事实的差异")


def session_scripts() -> dict[str, str]:
    """按小节切分剧本，支持一个文件装多个 session。

    有「## SXX｜」小节的按小节切，没有的整篇归到文件名对应的 session。
    """
    scripts: dict[str, str] = {}
    for path in sorted(ROOT.glob("sessions-S*.md")):
        m = re.match(r"sessions-(S\d{2})", path.name)
        if not m:
            continue
        text = path.read_text(encoding="utf-8")
        heads = list(SECTION_RE.finditer(text))
        if not heads:
            scripts.setdefault(m.group(1), text)
            continue
        for i, head in enumerate(heads):
            end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
            scripts[head.group(1)] = text[head.start():end]
    return scripts


def check_scripts(plants: list[dict]) -> None:
    scripts = session_scripts()
    if not scripts:
        warn("公开副本不含 session 剧本原文，跳过剧本级检查；结构化数据校验照常执行")
        return

    declared = {p["id"]: p for p in plants}
    seen: Counter[str] = Counter()

    for sid, text in scripts.items():
        for pid in TAG_RE.findall(text):
            seen[pid] += 1
            p = declared.get(pid)
            if p is None:
                err(f"{sid} 剧本引用了未登记的埋点：{pid}")
                continue
            if sid == p["input_session"]:
                continue
            if sid in p.get("allowed_sessions", []):
                warn(f"{sid} 剧本出现 {pid}，属授权复用（declared input={p['input_session']}）")
            else:
                err(f"{sid} 剧本出现 {pid}，但该 session 未授权")

    for pid, p in declared.items():
        if p["input_session"] in scripts and seen[pid] == 0:
            warn(f"{pid} 声明埋入 {p['input_session']}，但剧本里没有标签")

    # 关键词反泄漏：白名单外的 session 不得出现必记/可记事实关键词
    for pid, p in declared.items():
        if p["tier"] in {"限记-A", "限记-B", "禁记"}:
            continue
        for kw in p.get("keywords", []):
            for sid, text in scripts.items():
                if sid in p.get("allowed_sessions", []):
                    continue
                if kw in text:
                    err(f"关键词泄漏：{pid} 的关键词「{kw}」出现在未授权 session {sid}")

    # 输入剧本是否真的包含该埋点的关键词（提示待补剧本）
    for pid, p in declared.items():
        sid = p["input_session"]
        if sid not in scripts:
            continue
        text = scripts[sid]
        kws = p.get("keywords", [])
        if kws and not any(kw in text for kw in kws):
            warn(f"{pid} 剧本 {sid} 未出现关键词，剧本待补埋点")


def report(data: dict) -> dict:
    cps = data.get("checkpoints", [])
    plants = data.get("plants", [])
    total = len(cps)
    if not total:
        return {}

    trap = sum(1 for c in cps if c.get("trap"))
    diff = Counter(c["difficulty"][0] for c in cps if c.get("difficulty"))
    dim = Counter(str(c.get("dim", "")).split("/")[0].strip() for c in cps)
    dim_cross = sum(1 for c in cps if "/" in str(c.get("dim", "")))
    judge = Counter(c.get("judge", "") for c in cps)
    cites = sum(1 for c in cps if c.get("citations"))

    trap_ratio = trap / total
    target_trap = data.get("targets", {}).get("trap_ratio_min", 0.4)
    if trap_ratio < target_trap:
        warn(f"陷阱占比 {trap_ratio:.0%} 低于目标 {target_trap:.0%}")

    target_diff = data.get("targets", {}).get("difficulty", {})
    for level, share in target_diff.items():
        actual = diff.get(level, 0) / total
        if abs(actual - share) > 0.1:
            warn(f"难度「{level}」占比 {actual:.0%}，偏离目标 {share:.0%} 超过 10 个百分点")

    return {
        "total_checkpoints": total,
        "total_plants": len(plants),
        "trap_count": trap,
        "trap_ratio": round(trap_ratio, 3),
        "difficulty": dict(diff),
        "dimension": dict(dim),
        "dimension_cross": dim_cross,
        "judge": dict(judge),
        "citations_required": cites,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    data = load()
    if not data:
        print("\n".join(f"[错误] {e}" for e in errors), file=sys.stderr)
        return 1

    plants = data.get("plants", [])
    cps = data.get("checkpoints", [])
    plant_ids = {p.get("id") for p in plants}
    cp_ids = {c.get("id") for c in cps}

    check_plants(plants, cp_ids)
    check_checkpoints(cps, plant_ids)
    check_distractors(data.get("distractors", []), plant_ids)
    check_scripts(plants)
    stats = report(data)

    if args.json:
        print(json.dumps({"stats": stats, "errors": errors, "warnings": warnings},
                         ensure_ascii=False, indent=2))
        return 1 if errors else 0

    print("=" * 56)
    print("persona-01 题库校验报告")
    print("=" * 56)
    print(f"埋点 {stats['total_plants']} 个，检查点 {stats['total_checkpoints']} 个，"
          f"陷阱 {stats['trap_count']} 个（{stats['trap_ratio']:.0%}）")
    print(f"难度分布：{stats['difficulty']}")
    print(f"维度分布：{stats['dimension']}")
    print(f"判分方式：{stats['judge']}")
    print(f"要求引用：{stats['citations_required']} 题")
    print("-" * 56)

    if errors:
        print(f"错误 {len(errors)} 条")
        for e in errors:
            print(f"  [错误] {e}")
    if warnings:
        print(f"警告 {len(warnings)} 条")
        for w in warnings:
            print(f"  [警告] {w}")
    if not errors and not warnings:
        print("全部通过")
    print("-" * 56)
    print("结论：" + ("不通过" if errors else "通过"))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
