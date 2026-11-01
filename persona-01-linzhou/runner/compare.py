#!/usr/bin/env python3
"""对比两次运行的同一批检查点，输出条件和归因的变化。

用法：
    python3 compare.py --before results-batch3.json --after results.json
    python3 compare.py --before a.json --after b.json --cps CP15,CP17,CP18
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"


def load(name: str) -> dict:
    return json.loads((RESULTS / name).read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--cps", default="")
    args = ap.parse_args()

    a, b = load(args.before), load(args.after)
    cps = [x.strip() for x in args.cps.split(",") if x.strip()] or sorted(
        set(a["matrix"]) & set(b["matrix"]), key=lambda x: int(x[2:])
    )

    print(f"{'检查点':<8}{'条件':<20}{'归因':<22}{'C0 越权':<12}备注")
    print("-" * 78)
    changed = 0
    for cid in cps:
        ra, rb = a["matrix"].get(cid, {}), b["matrix"].get(cid, {})
        if not ra or not rb:
            print(f"{cid} 缺少一侧结果")
            continue
        def cell(row):
            return " ".join(f"{c}{'✓' if row[c]['passed'] else '✕'}" for c in ("C0", "C1", "C2", "C3"))
        ca, cb = cell(ra), cell(rb)
        la = (ra.get("attribution") or {}).get("label", "")
        lb = (rb.get("attribution") or {}).get("label", "")
        va = ",".join((ra.get("attribution") or {}).get("c0_violation") or []) or "—"
        vb = ",".join((rb.get("attribution") or {}).get("c0_violation") or []) or "—"
        notes = []
        for c in ("C0", "C1", "C2", "C3"):
            if ra[c]["passed"] != rb[c]["passed"]:
                notes.append(f"{c}{'↑' if rb[c]['passed'] else '↓'}")
                changed += 1
        if la != lb:
            notes.append("归因变化")
        if va != vb:
            notes.append("越权变化")
        print(f"{cid:<8}{ca} → {cb:<12}{la} → {lb:<14}{va} → {vb:<8}{'，'.join(notes) or '无变化'}")

    print("-" * 78)
    print(f"条件翻转 {changed} 处")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
