#!/usr/bin/env python3
"""把定点补跑的结果合并回原结果文件。

网关限流会随机产生一批 error run。runner 的 --retry-from 只重跑这些条目，
产出的是一个只有补跑条目的稀疏文件。本脚本把其中成功的条目写回原文件对应的
(cp, condition)，失败的保留原样，最后报告还剩多少 error。

用法：
    python3 merge_retry.py rep2-deepseek.json retry-deepseek.json
    python3 merge_retry.py rep2-deepseek.json retry-deepseek.json --out rep2-ds-fixed.json
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"


def load(p):
    p = Path(p)
    if not p.exists():
        p = RESULTS / p
    return p, json.loads(p.read_text())


def is_err(r):
    return bool((r.get("reply") or {}).get("error"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base", help="原结果文件")
    ap.add_argument("retry", help="补跑产出的稀疏结果文件")
    ap.add_argument("--out", default="", help="输出文件，默认原地覆盖 base")
    args = ap.parse_args()

    bp, base = load(args.base)
    rp, retry = load(args.retry)

    idx = {(r["cp"], r["condition"]): r for r in base["runs"]}
    filled = still_err = 0
    for r in retry["runs"]:
        if is_err(r):
            continue
        key = (r["cp"], r["condition"])
        if key in idx and is_err(idx[key]):
            idx[key] = r
            filled += 1

    base["runs"] = list(idx.values())
    still_err = sum(1 for r in base["runs"] if is_err(r))

    out = Path(args.out) if args.out else bp
    if not out.is_absolute():
        out = RESULTS / out
    out.write_text(json.dumps(base, ensure_ascii=False))

    print(f"{bp.name} + {rp.name} -> {out.name}")
    print(f"  补回 {filled} 条，剩余 error {still_err}/{len(base['runs'])}")
    if still_err:
        print("  仍失败的条目可再跑一次 --retry-from（网关错误通常第二次能成功）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
