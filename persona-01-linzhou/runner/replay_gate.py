#!/usr/bin/env python3
"""闸门离线重放：把基线回复重新过一遍闸门，测拦截与误伤（零 API、零采样噪声）。

为什么不用重新跑模型：闸门是确定性规则，同一回复同一上下文必然同一判定。
重跑会引入采样噪声，反而看不清闸门本身的效果。

用法：
    python3 replay_gate.py --src ../results/all-v2.json

输出：
    1. 拦截统计（按检查点、条件）
    2. 误伤：原本通过、加闸后不通过
    3. 修复：原本不通过（因越权）、加闸后通过
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import assertions
import conditions
import gate as gate_mod
from memory import NaiveMemory

ROOT = Path(__file__).resolve().parent.parent
CONDITIONS = ["C0", "C1", "C2", "C3"]


def load(name: str) -> dict:
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="../results/all-v2.json")
    args = ap.parse_args()

    src = json.loads(Path(args.src).read_text(encoding="utf-8"))
    persona = load("persona-01.json")
    spec = load("assertions.json")
    cpmap = {c["id"]: c for c in persona["checkpoints"]}
    sessions = conditions.load_sessions()
    memory = NaiveMemory()
    for sid in sorted(sessions, key=conditions.sid_index):
        memory.insert(sid, "\n".join(sessions[sid]["turns"]), conditions.sid_index(sid))

    blocked_cases = []
    fix, harm = [], []
    total_runs = 0
    for run in src["runs"]:
        cid, cond = run["cp"], run["condition"]
        if cid not in spec:
            continue
        cs = spec[cid]
        cp = {**cpmap[cid], "evidence": cs.get("evidence", [])}
        ctx = conditions.build(cp, cond, sessions, memory, 8000,
                               cs["trigger"], cs.get("turn"))
        reply = run["reply"]
        before = run["score"]["passed"]
        gated, rec = gate_mod.apply_gate(reply, ctx["text"], cs["trigger"])
        after = assertions.evaluate(gated, cs["rules"])["passed"]
        total_runs += 1
        if rec["triggered"]:
            blocked_cases.append((cid, cond, [b["tool"] for b in rec["blocked"]],
                                  [a["tool"] for a in rec["allowed"]]))
        if before and not after:
            harm.append((cid, cond))
        if not before and after:
            fix.append((cid, cond))

    print(f"重放 {total_runs} 条回复\n")
    print("## 一、拦截记录\n")
    print(f"共拦截 {len(blocked_cases)} 条：")
    for cid, cond, bl, al in sorted(blocked_cases, key=lambda x: (int(x[0][2:]), x[1])):
        extra = f"（同时放行 {','.join(al)}）" if al else ""
        print(f"- {cid} {cond}: 拦 {'、'.join(bl)}{extra}")
    print("\n按检查点汇总：", dict(Counter(c for c, *_ in blocked_cases)))

    print("\n## 二、误伤（原本通过，加闸后不通过）\n")
    if harm:
        for cid, cond in harm:
            print(f"- {cid} {cond}")
    else:
        print("- 无")

    print("\n## 三、修复（原本因越权失败，加闸后通过）\n")
    if fix:
        for cid, cond in fix:
            print(f"- {cid} {cond}")
    else:
        print("- 无")

    # 通过率变化
    before_pass = sum(1 for r in src["runs"] if r["score"]["passed"])
    print(f"\n通过率：{before_pass}/{total_runs} → "
          f"{before_pass + len(fix) - len(harm)}/{total_runs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
