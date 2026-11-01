#!/usr/bin/env python3
"""正则试验台：同一条正则在四家 × 四条件上的命中矩阵。

调加严判据时，直接改 json 再重放太慢。本脚本一次看全 16 条样本谁命中谁漏，
顺带打印漏判样本的原文，用于发现插入字、否定式误伤这类口径错误。

用法：
    python3 regex_lab.py CP18 '正则'
    python3 regex_lab.py CP18 --file ../data/patterns.json
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRCS = {'deepseek': 'all-v2.json', 'minimax': 'minimax-v2/all-v2.json',
        'glm': 'glm-v2/all-v2.json', 'hy4': 'hy4-v2/all-v2.json'}
CONDS = ["C0", "C1", "C2", "C3"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cp")
    ap.add_argument("pattern", nargs="?")
    ap.add_argument("--file", help="从 json 里取 {cp: pattern} 映射")
    ap.add_argument("--show", default="miss", choices=["miss", "hit", "all"])
    args = ap.parse_args()

    pat = args.pattern
    if args.file:
        pat = json.loads(Path(args.file).read_text()).get(args.cp, pat)
    if not pat:
        print("缺少正则")
        return 2
    rx = re.compile(pat)

    n_hit = 0
    print(f"{args.cp}  /{pat}/\n")
    print(f"  {'模型':<10}" + "".join(f"{c:<5}" for c in CONDS))
    for name, f in SRCS.items():
        d = json.loads((ROOT / "results" / f).read_text())
        cells, texts = [], {}
        for cond in CONDS:
            r = [x for x in d["runs"] if x["cp"] == args.cp and x["condition"] == cond]
            if not r:
                cells.append("?")
                continue
            t = str((r[0].get("reply") or {}).get("text", ""))
            texts[cond] = t
            hit = bool(rx.search(t))
            n_hit += hit
            cells.append("Y" if hit else ".")
        print(f"  {name:<10}" + "".join(f"{c:<5}" for c in cells))
    print(f"\n  命中 {n_hit}/16")

    if args.show != "none":
        print()
        for name, f in SRCS.items():
            d = json.loads((ROOT / "results" / f).read_text())
            for cond in CONDS:
                r = [x for x in d["runs"] if x["cp"] == args.cp and x["condition"] == cond]
                if not r:
                    continue
                t = str((r[0].get("reply") or {}).get("text", ""))
                hit = bool(rx.search(t))
                if args.show == "all" or (args.show == "miss" and not hit) \
                        or (args.show == "hit" and hit):
                    print(f"  [{name} {cond} {'命中' if hit else '漏'}] {t[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
