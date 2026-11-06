#!/usr/bin/env python3
"""P1-1：同一模型同一题目重复 N 次的方差估计。

回答的核心问题：
  单轮跑出来的结论（模型排序、废题判定、某题某条件的成败）里，
  有多少只是采样噪声？

口径：
  1) 轮间波动：每轮整体通过率 / 各条件通过率，跨轮的标准差
  2) 单题波动：同一题在同一轮内聚合 4 个条件，得到 3 个通过率，算标准差
     - 断言级：通过断言数 / 断言总数（连续量，噪声更敏感）
     - 题级：passed 二值的比例（离散量，紧贴验收线原文）
  3) 跨轮一致性：废题 / 零区分度判定是否在 3 轮里稳定

用法：
    python3 variance.py results/hy4-v2/a.json results/hy4-v2/b.json results/hy4-v2/c.json
"""

import argparse
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import assertions as A  # noqa: E402

CONDITIONS = ["C0", "C1", "C2", "C3"]
NOISE_LINE = 0.15  # 验收线：单题通过率标准差 < 0.15

SPEC = None  # 若指定另一份 spec，则用它的规则重新判分（离线重放，零调用）


def load(path):
    d = json.loads(Path(path).read_text())
    return d["meta"], d["runs"]


def run_stats(runs):
    """(cp, cond) -> (passed bool, 断言通过数, 断言总数)"""
    out = {}
    for r in runs:
        reply = r.get("reply") or {}
        if SPEC is not None and not reply.get("error"):
            rules = (SPEC.get(r["cp"]) or {}).get("rules")
            if rules:
                sc = A.evaluate(reply, rules)
            else:
                sc = r.get("score") or {}
        else:
            sc = r.get("score") or {}
        details = sc.get("details") or []
        ok = sum(1 for d in details if d.get("ok"))
        out[(r["cp"], r["condition"])] = (
            bool(sc.get("passed")), ok, len(details), r.get("perf") or {})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", default="", help="用另一份断言 spec 重放（如 assertions-v3.json）")
    ap.add_argument("files", nargs="+")
    args = ap.parse_args()
    paths = args.files

    global SPEC
    if args.spec:
        SPEC = json.loads(Path(args.spec).read_text())
        print(f"重放 spec：{Path(args.spec).name}\n")

    if len(paths) < 2:
        print("需要至少两个 run 文件")
        return 2

    metas, all_stats, all_runs = [], [], []
    for p in paths:
        m, runs = load(p)
        metas.append(m)
        all_stats.append(run_stats(runs))
        all_runs.append(runs)

    model = metas[0].get("model", "?")
    n_rep = len(paths)
    print(f"模型 {model}  重复 {n_rep} 轮  每题 {len(CONDITIONS)} 条件")
    for m in metas:
        err = m.get("stats", {}).get("call_errors", 0)
        print(f"  run {m['run_id']}  runs={m['coverage']['with_rules']}题  "
              f"elapsed={m.get('elapsed_s','?')}s  call_errors={err}")
    print()

    cps = sorted({c for s in all_stats for c, _ in s})

    # ---------- 1) 轮间整体波动 ----------
    print("=" * 72)
    print("1. 轮间波动：单轮结论的可信度")
    print("=" * 72)
    overall = []
    for i, s in enumerate(all_stats):
        tot = sum(1 for k in s if s[k][0])
        n = len(s)
        overall.append(tot / n)
        print(f"  第{i+1}轮 整体通过 {tot}/{n} = {tot/n:.1%}")
    sd_all = st.pstdev(overall)
    print(f"  轮间标准差 {sd_all:.4f} ({sd_all*100:.2f}pp)  "
          f"极差 {(max(overall)-min(overall))*100:.2f}pp")
    print(f"  含义：两次运行的分数差小于约 {2*sd_all*100:.1f}pp 时，不能认为模型真有差距")
    print()

    print("  分条件（每轮 63 题的通过率）：")
    print(f"  {'条件':<6}" + "".join(f"第{i+1}轮  " for i in range(n_rep)) + " 标准差   极差")
    cond_sd = {}
    for cond in CONDITIONS:
        vals = []
        for s in all_stats:
            keys = [k for k in s if k[1] == cond]
            vals.append(sum(1 for k in keys if s[k][0]) / len(keys))
        sd = st.pstdev(vals)
        cond_sd[cond] = sd
        cells = "".join(f"{v:>6.1%} " for v in vals)
        print(f"  {cond:<6}{cells}  {sd*100:>5.2f}pp  {(max(vals)-min(vals))*100:>5.2f}pp")
    print()

    # 记忆增益 C1-C0 的轮间波动
    gains = []
    for s in all_stats:
        g = {}
        for cond in CONDITIONS:
            keys = [k for k in s if k[1] == cond]
            g[cond] = sum(1 for k in keys if s[k][0]) / len(keys)
        gains.append(g["C1"] - g["C0"])
    print("  记忆增益 C1−C0：" + "  ".join(f"第{i+1}轮 {v*100:+.1f}pp" for i, v in enumerate(gains))
          + f"   标准差 {st.pstdev(gains)*100:.2f}pp")
    print()

    # ---------- 2) 单题波动 ----------
    print("=" * 72)
    print(f"2. 单题波动（验收线：标准差 < {NOISE_LINE}）")
    print("=" * 72)
    rows = []
    for cp in cps:
        assert_rates, cp_rates = [], []
        for s in all_stats:
            keys = [k for k in s if k[0] == cp]
            if not keys:
                continue
            ok = sum(s[k][1] for k in keys)
            tot = sum(s[k][2] for k in keys)
            assert_rates.append(ok / tot if tot else 0.0)
            cp_rates.append(sum(1 for k in keys if s[k][0]) / len(keys))
        if len(assert_rates) < 2:
            continue
        rows.append({
            "cp": cp,
            "asr": assert_rates,
            "asr_sd": st.pstdev(assert_rates),
            "asr_mean": st.fmean(assert_rates),
            "cpr": cp_rates,
            "cp_sd": st.pstdev(cp_rates),
            "cp_mean": st.fmean(cp_rates),
            "n_assert": sum(s[k][2] for k in all_stats[0] if k[0] == cp),
        })

    over_a = [r for r in rows if r["asr_sd"] > NOISE_LINE]
    over_c = [r for r in rows if r["cp_sd"] > NOISE_LINE]
    print(f"  断言级：{len(over_a)}/{len(rows)} 题标准差 > {NOISE_LINE}"
          f"   中位 {st.median([r['asr_sd'] for r in rows]):.3f}"
          f"   均值 {st.fmean([r['asr_sd'] for r in rows]):.3f}")
    print(f"  题级  ：{len(over_c)}/{len(rows)} 题标准差 > {NOISE_LINE}"
          f"   中位 {st.median([r['cp_sd'] for r in rows]):.3f}"
          f"   均值 {st.fmean([r['cp_sd'] for r in rows]):.3f}")
    print()
    print("  断言级波动最大的 12 题（这些题的单轮结论最不可信）：")
    print(f"  {'题':<6}{'断言数':>6}{'均值':>8}{'标准差':>8}  三轮逐轮通过率")
    for r in sorted(rows, key=lambda x: -x["asr_sd"])[:12]:
        seq = " ".join(f"{v:.2f}" for v in r["asr"])
        print(f"  {r['cp']:<6}{r['n_assert']:>6}{r['asr_mean']:>8.2f}{r['asr_sd']:>8.3f}  {seq}")
    print()
    stable = sorted(rows, key=lambda x: x["asr_sd"])[:8]
    print("  最稳定的 8 题（可当回归锚点）：")
    print(f"  {'题':<6}{'断言数':>6}{'均值':>8}{'标准差':>8}  三轮逐轮通过率")
    for r in stable:
        seq = " ".join(f"{v:.2f}" for v in r["asr"])
        print(f"  {r['cp']:<6}{r['n_assert']:>6}{r['asr_mean']:>8.2f}{r['asr_sd']:>8.3f}  {seq}")
    print()

    # ---------- 3) 跨轮一致性 ----------
    print("=" * 72)
    print("3. 跨轮一致性：废题 / 零区分度判定")
    print("=" * 72)
    verdict = defaultdict(list)
    for s in all_stats:
        for cp in cps:
            keys = [k for k in s if k[0] == cp]
            if not keys:
                continue
            flags = [s[k][0] for k in keys]
            if all(flags):
                verdict[cp].append("全通过")
            elif not any(flags):
                verdict[cp].append("全失败")
            else:
                verdict[cp].append("有区分")
    inconsistent = {cp: v for cp, v in verdict.items() if len(set(v)) > 1}
    always_flat = {cp: v[0] for cp, v in verdict.items()
                   if len(set(v)) == 1 and v[0] != "有区分"}
    print(f"  判定在 {n_rep} 轮里不一致的题：{len(inconsistent)}/{len(verdict)}")
    for cp, v in sorted(inconsistent.items()):
        print(f"    {cp}: {' / '.join(v)}   <-- 单轮判定不可信")
    print()
    print(f"  每轮都无区分度的题：{len(always_flat)}")
    for cp, v in sorted(always_flat.items()):
        print(f"    {cp}: {v}")
    print()

    # ---------- 4) 结论 ----------
    print("=" * 72)
    print("4. 对已有结论的影响")
    print("=" * 72)
    print(f"  轮间整体标准差 {sd_all*100:.2f}pp → 模型间差异需大于约 "
          f"{2*sd_all*100:.1f}pp 才可判为真实差距")
    print(f"  四模型实测总分极差 4pp（minimax 60% ~ hy4 64%）")
    verdict_txt = ("在噪声内，排序不可信" if 0.04 < 2 * sd_all
                   else "大于噪声，排序可用")
    print(f"  判定：{verdict_txt}")
    print()
    print("  条件级噪声（该条件的单轮分数要差多少才算真变化）：")
    for cond in CONDITIONS:
        print(f"    {cond}: ±{2*cond_sd[cond]*100:.1f}pp")
    return 0


if __name__ == "__main__":
    sys.exit(main())
