#!/usr/bin/env python3
"""Hy4 思考开 vs 思考关的同题对照（样本量小，只作配置说明用）。"""

import json
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent.parent
R = ROOT / "results"

think = json.loads((R / "results-v2-hy4-think.json").read_text(encoding="utf-8"))
off = json.loads((R / "hy4-v2" / "all-v2.json").read_text(encoding="utf-8"))
others = {k: json.loads((R / v).read_text(encoding="utf-8")) for k, v in {
    "deepseek": "all-v2.json",
    "minimax": "minimax-v2/all-v2.json",
    "glm": "glm-v2/all-v2.json",
}.items()}

cps = sorted({r["cp"] for r in think["runs"]})
print("思考开样本 CP：", cps, f"（{len(think['runs'])} 次调用）\n")
print("| CP | hy4 思考开 | hy4 思考关 | deepseek | minimax | glm |")
print("|---|---|---|---|---|---|")
for c in cps:
    cells = []
    for src in (think, off):
        rs = [r for r in src["runs"] if r["cp"] == c]
        cells.append(f"{sum(1 for r in rs if r['score']['passed'])}/{len(rs)}")
    for name, d in others.items():
        rs = [r for r in d["runs"] if r["cp"] == c]
        cells.append(f"{sum(1 for r in rs if r['score']['passed'])}/{len(rs)}")
    print(f"| {c} | " + " | ".join(cells) + " |")

lt = [r["perf"]["latency_ms"] for r in think["runs"]]
ln = [r["perf"]["latency_ms"] for r in off["runs"] if r["cp"] in cps]
to = sum(r["perf"].get("tokens_out", 0) for r in think["runs"]) // max(len(think["runs"]), 1)
no = sum(r["perf"].get("tokens_out", 0) for r in off["runs"] if r["cp"] in cps) // max(len(ln), 1)
print(f"\n延迟中位：思考开 {median(lt)/1000:.0f}s vs 思考关 {median(ln)/1000:.1f}s")
print(f"输出 token 均值：思考开 {to} vs 思考关 {no}")
print(f"思考开样本通过率：{sum(1 for r in think['runs'] if r['score']['passed'])}/{len(think['runs'])}")
print(f"同题思考关通过率：{sum(1 for r in off['runs'] if r['cp'] in cps and r['score']['passed'])}/{len(ln)}")
