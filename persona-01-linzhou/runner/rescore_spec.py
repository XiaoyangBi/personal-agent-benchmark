#!/usr/bin/env python3
"""用另一份断言 spec 离线重放已有结果，零成本对比新旧量尺。

改断言等于改量尺：历史分数会立刻不可比。所以加严断言一律先建新 spec 文件
（如 assertions-v3.json），用本脚本离线重放，确认通过率落在有区分度的区间
（经验区间 20%~80%）之后再决定是否并入主 spec。

用法：
    python3 rescore_spec.py --spec ../data/assertions-v3.json \
        results/all-v2.json results/minimax-v2/all-v2.json ...

输出：逐题新旧通过数对比 + 只列出发生变化的题。
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import assertions as A  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONDITIONS = ["C0", "C1", "C2", "C3"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True, help="新 spec 路径")
    ap.add_argument("--cps", default="", help="只看这些题，逗号分隔；空=全部")
    ap.add_argument("--show-reply", action="store_true", help="打印变化题的回复文本")
    ap.add_argument("files", nargs="+")
    args = ap.parse_args()

    new_spec = json.loads(Path(args.spec).read_text())
    want = {x.strip() for x in args.cps.split(",") if x.strip()}

    for f in args.files:
        p = Path(f)
        if not p.exists():
            p = ROOT / "results" / f
        d = json.loads(p.read_text())
        model = d["meta"].get("model", p.parent.name)
        print("=" * 74)
        print(f"{model}   run {d['meta']['run_id']}   spec {Path(args.spec).name}")
        print("=" * 74)

        changed, tot_old, tot_new = [], 0, 0
        per_cp = defaultdict(lambda: [0, 0, 0])  # cp -> [old_pass, new_pass, n]

        for r in d["runs"]:
            cp = r["cp"]
            if want and cp not in want:
                continue
            rules = (new_spec.get(cp) or {}).get("rules")
            if not rules:
                continue
            reply = r.get("reply") or {}
            if reply.get("error"):
                continue
            old = bool((r.get("score") or {}).get("passed"))
            res = A.evaluate(reply, rules)
            new = bool(res["passed"])
            per_cp[cp][0] += old
            per_cp[cp][1] += new
            per_cp[cp][2] += 1
            tot_old += old
            tot_new += new
            if old != new:
                changed.append((cp, r["condition"], old, new, res, reply))

        n = sum(v[2] for v in per_cp.values())
        if n:
            print(f"  涉及题 {len(per_cp)}  样本 {n}  旧通过 {tot_old} ({tot_old/n:.0%})"
                  f"  →  新通过 {tot_new} ({tot_new/n:.0%})")
        print()
        print(f"  {'题':<7}{'旧':>5}{'新':>5}{'样本':>6}  变化")
        for cp in sorted(per_cp):
            o, nw, k = per_cp[cp]
            flag = "" if o == nw else ("  <-- 变难" if nw < o else "  <-- 变易")
            print(f"  {cp:<7}{o:>5}{nw:>5}{k:>6}{flag}")
        print()
        if changed:
            print(f"  翻转样本 {len(changed)} 条：")
            for cp, cond, o, nw, res, reply in changed:
                print(f"    {cp} {cond}: {o} -> {nw}")
                for det in res["details"]:
                    if not det["ok"]:
                        print(f"       未过：{det['msg'][:110]}")
                if args.show_reply:
                    print(f"       回复：{str(reply.get('text',''))[:220]}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
