#!/usr/bin/env python3
"""把多次运行的结果合并成一份全量结果，并统计异常题。

规则：同一个检查点以最新一次运行（run_id 时间戳最大）为准。
用法：
    python3 aggregate.py
输出：
    results/all.json
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
sys.path.insert(0, str(Path(__file__).resolve().parent))

import runner  # noqa: E402

ABNORMAL = {"记忆污染", "检索未命中", "读取失败", "能力失败", "记忆生效·oracle异常", "越权执行"}
DESIGN = {"废题"}


def load_persona() -> dict:
    return json.loads((ROOT / "data" / "persona-01.json").read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="", help="结果目录，相对 persona 根目录，默认 results/")
    ap.add_argument("--out", default="all.json", help="合并结果文件名")
    args = ap.parse_args()

    persona = load_persona()
    cpmap = {c["id"]: c for c in persona["checkpoints"]}

    src_dir = ROOT / args.dir if args.dir else RESULTS
    files = sorted(src_dir.glob("results*.json"))
    files = [f for f in files if f.name not in {"all.json", args.out}]
    if not files:
        print("没有可合并的结果文件")
        return 1

    latest: dict[str, tuple[str, dict, dict]] = {}  # cp -> (run_id, file, row)
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("meta", {}).get("mode") in {"merged", "dry_run"}:
            continue  # 只吃真实运行的原始结果
        run_id = data.get("meta", {}).get("run_id", "")
        for cid, row in data.get("matrix", {}).items():
            if cid not in cpmap:
                continue
            if cid not in latest or run_id > latest[cid][0]:
                latest[cid] = (run_id, data, row)

    matrix, runs, sources = {}, [], []
    for cid in sorted(latest, key=lambda x: int(x[2:])):
        run_id, data, row = latest[cid]
        if all(k in row for k in ("C0", "C1", "C2", "C3")):
            row["attribution"] = runner.attribution(cpmap[cid], row, row["retrieval"])
        matrix[cid] = row
        runs += [r for r in data.get("runs", []) if r["cp"] == cid]
        sources.append((cid, run_id))

    label = Counter((row.get("attribution") or {}).get("label", "未归因") for row in matrix.values())
    mode = Counter((row.get("attribution") or {}).get("c1_failure", {}).get("mode", "")
                   for row in matrix.values() if "C1" in row and not row["C1"]["passed"])
    violate = [cid for cid, row in matrix.items()
               if (row.get("attribution") or {}).get("c0_violation")]
    c1_fail = [cid for cid, row in matrix.items() if "C1" in row and not row["C1"]["passed"]]

    # 否认历史：模型主动宣称上下文里没有该信息。不限于失败题，
    # 即使最终答对，中途说「这段历史里没提到」也是问题。
    deny_by_cond: dict[str, dict] = {}
    deny_cps: dict[str, list] = {}
    for run in runs:
        cond = run.get("condition", "")
        if run.get("reply", {}).get("error"):
            continue
        d = deny_by_cond.setdefault(cond, {"n": 0, "deny": 0})
        d["n"] += 1
        if runner.has_deny(run.get("reply", {}).get("text", "")):
            d["deny"] += 1
            deny_cps.setdefault(cond, []).append(run["cp"])
    deny_rate = {c: round(v["deny"] / v["n"], 3) for c, v in deny_by_cond.items() if v["n"]}

    abnormal_label = [cid for cid, row in matrix.items()
                      if (row.get("attribution") or {}).get("label") in ABNORMAL]
    abnormal_all = sorted(set(abnormal_label) | set(violate), key=lambda x: int(x[2:]))

    design_issue = [cid for cid, row in matrix.items()
                    if (row.get("attribution") or {}).get("label") in DESIGN]
    trap_cps = [cid for cid, cp in cpmap.items() if cp.get("trap") and cid in matrix]
    trap_missed = [cid for cid in trap_cps
                   if all(matrix[cid][c]["passed"] for c in ("C0", "C1", "C2", "C3"))]

    stats = {
        "checkpoints": len(matrix),
        "abnormal_label": len(abnormal_label),
        "abnormal_label_ratio": round(len(abnormal_label) / len(matrix), 3) if matrix else 0,
        "abnormal_union": len(abnormal_all),
        "abnormal_union_ratio": round(len(abnormal_all) / len(matrix), 3) if matrix else 0,
        "abnormal_list": abnormal_all,
        "design_issue": design_issue,
        "trap_total": len(trap_cps),
        "trap_missed": trap_missed,
        "labels": dict(label),
        "c0_violation": violate,
        "c1_fail": c1_fail,
        "c1_fail_modes": {k: v for k, v in mode.items() if k},
        "deny_by_condition": deny_by_cond,
        "deny_rate": deny_rate,
        "deny_cps": deny_cps,
        "sources": dict(sources),
    }

    model = "unknown"
    for cid, row in latest.items():
        src = latest[cid][1].get("meta", {})
        if src.get("model"):
            model = src["model"]
            break

    out = {
        "meta": {
            "persona": persona["persona_id"],
            "mode": "merged",
            "model": model,
            "conditions": ["C0", "C1", "C2", "C3"],
            "coverage": {"with_rules": len(matrix), "total": len(persona["checkpoints"])},
            "budget": 8000,
            "run_id": "merged-" + max(v[0] for v in latest.values()),
        },
        "runs": runs,
        "matrix": matrix,
        "stats": stats,
    }
    path = src_dir / args.out
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"合并 {len(files)} 份结果，覆盖 {len(matrix)} 个检查点")
    print(f"标签分布：{dict(label)}")
    print(f"异常题（模型侧）：{len(abnormal_label)} / {len(matrix)} = {stats['abnormal_label_ratio']:.0%}")
    print(f"异常题（含 C0 越权）：{len(abnormal_all)} / {len(matrix)} = {stats['abnormal_union_ratio']:.0%}")
    print(f"题目待修（废题）：{design_issue or '无'}")
    print(f"陷阱未触发：{trap_missed or '无'}（共 {len(trap_cps)} 个陷阱题）")
    print(f"C0 越权：{violate or '无'}")
    print(f"C1 失败：{len(c1_fail)} 题，模式 {stats['c1_fail_modes']}")
    print(f"否认历史率（各条件）：{ {k: f'{v:.0%}' for k, v in deny_rate.items()} }")
    print(f"合并结果写入 {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
