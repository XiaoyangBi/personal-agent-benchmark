#!/usr/bin/env python3
"""排序稳健性检验：把两家的差异拆到检查点级，看排名是"普遍领先"还是"几题侥幸"。

为什么不继续加轮次：
聚合分数把 63 个检查点压成一个数，检查点之间的巨大差异（有的恒 0、有的恒 1）
全被算进轮间波动里，于是需要很多轮才能把 2pp 的差分辨出来。改用检查点级符号检验，
不依赖正态假设、不受 glm sd 估到 0.20pp 这种小样本假精确影响，直接回答：
"glm 比 hy4 高 2.4pp，是靠多数检查点赢，还是靠两三个检查点？"

口径：
  1. 每个 (cp, cond) 条目在每轮的通过与否取均值 → 该条目的通过率
  2. 同一检查点下 4 个条件取均值 → 该检查点的得分
  3. 两两比较：A 赢 / 平 / 输 的检查点数，对非平局做精确二项检验（p=0.5）
  4. 平局阈值默认 1pp（低于这个量级视为并列，不投票）

用法：
    python3 rank_robust.py --spec ../data/assertions-v3.json
"""

import argparse
import itertools
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import assertions as A  # noqa: E402
import stats_util as S  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# 每家模型的逐轮结果文件（与 variance_multi.py 的最终四家对比一致）
MODELS = {
    "deepseek": ["results/all-v2.json", "results/rep2-deepseek.json",
                 "results/rep3-deepseek.json", "results/rep4-deepseek.json"],
    "minimax":  ["results/minimax-v2/all-v2.json", "results/rep2-minimax.json",
                 "results/rep3-minimax-full.json", "results/rep4-minimax.json"],
    "glm":      ["results/glm-v2/all-v2.json", "results/rep2-glm.json"],
    "hy4":      ["results/hy4-v2/results-v2-full-hy4b.json",
                 "results/hy4-v2/results-v2-hy4-rep2.json",
                 "results/hy4-v2/results-v2-hy4-rep3.json"],
    "mimo":     ["results/rep1-mimo.json", "results/rep2-mimo.json",
                 "results/rep3-mimo.json"],
}


def load(path, spec):
    """读一轮结果，返回 {(cp, cond): passed bool}，error 条目丢弃。"""
    data = json.loads((ROOT / path).read_text())
    out = {}
    for r in data.get("runs") or []:
        reply = r.get("reply") or {}
        if reply.get("error"):
            continue
        rules = (spec.get(r["cp"]) or {}).get("rules") or []
        sc = A.evaluate(reply, rules) if rules else (r.get("score") or {})
        out[(r["cp"], r["condition"])] = bool(sc.get("passed"))
    return out


def binom_two_sided(k, n):
    """精确二项检验（p=0.5）双侧 p 值。"""
    if n == 0:
        return 1.0
    pmf = [math.comb(n, i) * 0.5 ** n for i in range(n + 1)]
    obs = pmf[k]
    # 双侧：把所有概率 <= 观测点概率的结果加起来（比 2×单侧尾巴稳，不会超 1）
    return min(1.0, sum(p for p in pmf if p <= obs + 1e-12))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", default="data/assertions-v3.json")
    ap.add_argument("--tie", type=float, default=0.01,
                    help="检查点得分差小于此值算平局（比例，默认 1pp）")
    args = ap.parse_args()

    spec = json.loads((ROOT / args.spec).read_text())

    # 每家的逐轮条目
    per_model = {}   # model -> {item: [bool, ...]}
    for name, files in MODELS.items():
        seq = {}
        for f in files:
            for k, v in load(f, spec).items():
                seq.setdefault(k, []).append(v)
        per_model[name] = seq

    # 全局交集：只保留每家每一轮都成功跑到的条目
    all_items = None
    for name, files in MODELS.items():
        n_rounds = len(files)
        ks = {k for k, v in per_model[name].items() if len(v) == n_rounds}
        all_items = ks if all_items is None else (all_items & ks)
    items = sorted(all_items)

    cps = sorted({cp for cp, _ in items})

    print("=" * 88)
    print("排序稳健性：检查点级符号检验")
    print("=" * 88)
    print()
    print(f"  全局交集 {len(items)} 条（{len(cps)} 个检查点 × 4 条件）")
    print(f"  各家轮次： " + "、".join(
        f"{n} {sum(1 for k, v in per_model[n].items() if len(v) == len(fs))}条/{len(fs)}轮"
        for n, fs in MODELS.items()))
    print()

    # 条目通过率 → 检查点得分
    score = {}   # model -> {cp: 得分}
    for name in MODELS:
        bycp = {}
        for cp, cond in items:
            bycp.setdefault(cp, []).append(
                sum(per_model[name][(cp, cond)]) / len(per_model[name][(cp, cond)]))
        score[name] = {cp: sum(v) / len(v) for cp, v in bycp.items()}

    overall = {n: sum(score[n].values()) / len(cps) for n in MODELS}

    print("-" * 88)
    print("1. 总体得分（检查点均值，与聚合口径应一致）")
    print("-" * 88)
    for n in sorted(MODELS, key=lambda x: -overall[x]):
        print(f"  {n:<10} {overall[n]*100:>6.1f}%")
    print()

    print("-" * 88)
    print(f"2. 两两比较：三种检验并列（平局阈值 {args.tie*100:.0f}pp）")
    print("-" * 88)

    def sd_of_rounds(name):
        """该模型逐轮总分的样本标准差（ddof=1）。"""
        rounds = len(MODELS[name])
        pcts = []
        for r in range(rounds):
            vals = [per_model[name][it][r] for it in items
                    if r < len(per_model[name][it])]
            if vals:
                pcts.append(sum(vals) / len(vals))
        if len(pcts) < 2:
            return 0.0
        m = sum(pcts) / len(pcts)
        return (sum((x - m) ** 2 for x in pcts) / (len(pcts) - 1)) ** 0.5

    thr = 2 * max(sd_of_rounds(n) for n in MODELS)
    print(f"{'对比':<20}{'得分差':>8}{'阈值法':>9}{'配对Welch':>10}{'p':>7}"
          f"{'符号p':>8}{'票数':>11}   综合判定")
    print("-" * 88)
    pairs = list(itertools.combinations(sorted(MODELS, key=lambda x: -overall[x]), 2))
    results = []
    for ka, kb in pairs:
        w = t = l = 0
        for cp in cps:
            d = score[ka][cp] - score[kb][cp]
            if d > args.tie:
                w += 1
            elif d < -args.tie:
                l += 1
            else:
                t += 1
        n = w + l
        p_sign = binom_two_sided(w, n)
        d, se, tv, df, p_w = S.welch(overall[ka], sd_of_rounds(ka), len(MODELS[ka]),
                                     overall[kb], sd_of_rounds(kb), len(MODELS[kb]))
        dp = d * 100
        thr_v = "可分" if dp > thr * 100 else "不可分"
        w_v = "可分" if p_w < 0.05 else "不可分"
        s_v = "可分" if p_sign < 0.05 else "不可分"
        agree = sum(1 for v in (thr_v, w_v, s_v) if v == "可分")
        final = "可分" if agree == 3 else ("不可分" if agree == 0 else "证据不足")
        results.append((ka, kb, dp, w, t, l, p_sign, p_w, thr_v, w_v, s_v, final))
        print(f"{ka+' vs '+kb:<20}{dp:>7.1f}pp{thr_v:>9}{w_v:>10}{p_w:>7.3f}"
              f"{p_sign:>8.3f}{f'{w}:{l}/平{t}':>11}   {final}")

    print()
    print(f"  可信阈值 {thr*100:.1f}pp（各模型单轮 sd 最大值 × 2）")
    print("  阈值法：全局单一门槛，偏保守——不含最大噪声模型的那对会被压回不可分")
    print("  配对 Welch：用这一对自身的标准误，随轮次收敛")
    print("  符号检验：按检查点投票，只看方向不看幅度")

    print()
    print("-" * 88)
    print("3. 差异是不是集中在少数检查点")
    print("-" * 88)
    print()
    for ka, kb, dp, w, t, l, p_sign, p_w, thr_v, w_v, s_v, final in results:
        if abs(dp) < 1.0:
            continue
        diffs = sorted(((abs(score[ka][cp] - score[kb][cp]), cp) for cp in cps),
                       reverse=True)
        top3 = sum(d for d, _ in diffs[:3])
        total = sum(d for d, _ in diffs)
        share = top3 / total * 100 if total else 0
        names = "、".join(cp for _, cp in diffs[:3])
        print(f"  {ka} vs {kb}  （{dp:+.1f}pp）")
        print(f"    差异最大的 3 个检查点贡献 {share:.0f}% 的总差距：{names}")
        print(f"    领先检查点 {w} 个 / 落后 {l} 个，中位差距 "
              f"{sorted((abs(score[ka][cp]-score[kb][cp]) for cp in cps))[len(cps)//2]*100:.0f}pp")
        print()

    print("=" * 88)
    print("判读")
    print("=" * 88)
    print()
    print("  符号检验不问'差多少分'，只问'差在哪几题'。若 A 在多数检查点上稳定")
    print("  领先，即使总分只差 2pp，排序也是真的；若靠 3 个检查点拉起来，则是侥幸。")
    print("  平局按 1pp 内不算，避免把采样抖动当成胜负票。")
    print()


if __name__ == "__main__":
    main()
