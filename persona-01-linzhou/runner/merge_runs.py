#!/usr/bin/env python3
"""把补跑文件里 base 中缺失的 (cp, condition) 条目追加回 base。

与 merge_retry.py 的区别：
  merge_retry.py  只填 base 中已存在但报错的条目（网关限流造成）
  merge_runs.py   追加 base 里根本没有的条目（跑一半被中断、缺整段检查点）

两种情况都会出现在实测里：一次跑 63 个检查点，中途被杀会留下"缺 CP56~CP63"，
被限流打断会留下"CPxx 的 C1 报错"。

用法：
    python3 merge_runs.py rep3-minimax.json rep3b-minimax.json
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
    ap.add_argument("extra", help="补跑产出的文件")
    ap.add_argument("--out", default="", help="输出文件，默认原地覆盖 base")
    args = ap.parse_args()

    bp, base = load(args.base)
    ep, extra = load(args.extra)

    idx = {(r["cp"], r["condition"]): r for r in base["runs"]}
    added = skipped = 0
    for r in extra["runs"]:
        key = (r["cp"], r["condition"])
        if key in idx:
            skipped += 1
            continue
        idx[key] = r
        added += 1

    base["runs"] = list(idx.values())
    still_err = sum(1 for r in base["runs"] if is_err(r))

    out = Path(args.out) if args.out else bp
    if not out.is_absolute():
        out = RESULTS / out
    out.write_text(json.dumps(base, ensure_ascii=False))

    cps = sorted({r["cp"] for r in base["runs"]})
    print(f"{bp.name} + {ep.name} -> {out.name}")
    print(f"  新增 {added} 条，跳过重复 {skipped} 条")
    print(f"  覆盖 {len(cps)}/63 个检查点，共 {len(base['runs'])} 次运行，剩余 error {still_err}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
