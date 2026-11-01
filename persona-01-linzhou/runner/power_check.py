#!/usr/bin/env python3
"""
排序可分性检验：回答"再补多少轮才能把梯队内排序分开"。

为什么需要这个：
variance_multi.py 用的阈值法是 "差 > 2 × 各模型 sd 的最大值"，这个门槛只与
单轮抖动有关，与轮次 n 无关——补多少轮它都不会变。用它做梯队内排序，
glm vs hy4（差 2.3pp）永远小于 3.2pp，结论恒定"不可分"，补轮次是白跑。

两种口径回答的是两个不同问题：
  阈值法  —— 单轮结果差这么多，是噪声吗？（用于判断某一次跑分是否可信）
  Welch t —— 多轮均值差这么多，是噪声吗？（用于判断排序，随 n 收敛）

用法：python3 power_check.py
"""

import math

# 各模型：逐轮分数（百分比）、sd（pp）
M = {
    "deepseek": dict(n=4, mean=53.9, sd=1.58, runs=[56.6, 52.6, 53.0, 53.4]),
    "minimax":  dict(n=2, mean=55.4, sd=0.80, runs=[56.2, 54.6]),
    "glm":      dict(n=2, mean=60.8, sd=0.20, runs=[60.6, 61.0]),
    "hy4":      dict(n=3, mean=58.4, sd=1.47, runs=[58.6, 60.2, 56.6]),
}


def welch(a, b):
    """返回 (均值差, 差的标准误, t, Welch 自由度)。"""
    va, vb = a["sd"] ** 2, b["sd"] ** 2
    na, nb = a["n"], b["n"]
    se = math.sqrt(va / na + vb / nb)
    d = a["mean"] - b["mean"]
    if se == 0:
        return d, 0.0, float("inf"), float("inf")
    t = d / se
    df_num = (va / na + vb / nb) ** 2
    df_den = (va / na) ** 2 / max(na - 1, 1) + (vb / nb) ** 2 / max(nb - 1, 1)
    df = df_num / df_den if df_den else float("inf")
    return d, se, t, df


def t_crit(df, alpha=0.05):
    """双侧 t 临界值，小自由度用表，大自由度用正态近似。"""
    table = {1: 12.71, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
             6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
             12: 2.179, 15: 2.131, 20: 2.086, 30: 2.042}
    if df == float("inf"):
        return 1.96
    if df in table:
        return table[df]
    lo = max(k for k in table if k <= df) if df >= 1 else 1
    if df > 30:
        return 1.96
    hi = min(k for k in table if k >= df)
    # 线性插值，够用
    w = (df - lo) / (hi - lo)
    return table[lo] * (1 - w) + table[hi] * w


def need_n(sd_a, sd_b, d, df_guess=10):
    """两模型各需多少轮才能让均值差显著（假定真实差 = 当前观测差）。"""
    if d == 0:
        return None
    for n in range(2, 200):
        se = math.sqrt(sd_a ** 2 / n + sd_b ** 2 / n)
        t = d / se
        # 自由度近似 2n-2（等样本量时接近 Welch）
        if t >= t_crit(2 * n - 2):
            return n
    return None


print("=" * 84)
print("排序可分性检验：阈值法 vs Welch t 检验")
print("=" * 84)
print()
print("口径说明：")
print("  阈值法   判定标准  |均值差| > 2 × 各模型 sd 的最大值（当前 3.2pp）")
print("           这个门槛只与单轮抖动有关，与轮次无关。补轮次它不会降。")
print("  Welch t  判定标准  |均值差| > t(0.05, df) × se_diff")
print("           se_diff 随轮次按 1/√n 收敛，补轮次会变松。")
print()

thr = 2 * max(m["sd"] for m in M.values())
print(f"当前阈值（阈值法）：{thr:.1f}pp")
print()

pairs = [("glm", "hy4"), ("minimax", "deepseek"), ("hy4", "minimax"),
         ("glm", "minimax"), ("glm", "deepseek"), ("hy4", "deepseek")]

print("-" * 84)
print(f"{'对比':<22}{'均值差':>8}{'se_diff':>10}{'t':>8}{'df':>7}{'t临界':>8}   判定")
print("-" * 84)
for ka, kb in pairs:
    a, b = M[ka], M[kb]
    d, se, t, df = welch(a, b)
    tc = t_crit(df)
    verdict = "可分" if abs(t) > tc else "不可分"
    print(f"{ka+' vs '+kb:<22}{d:>7.1f}pp{se:>9.2f}pp{t:>8.2f}{df:>7.1f}{tc:>8.2f}   {verdict}")

print()
print("=" * 84)
print("要让它分得开，各模型还要跑多少轮")
print("=" * 84)
print()
print("（假定真实差 = 当前观测差；若真实差更小，需要的轮次会更多，下面的数是下限）")
print()
print("-" * 84)
print(f"{'对比':<22}{'现状':>10}{'需各跑':>8}{'还需补':>10}   值不值")
print("-" * 84)
for ka, kb in [("glm", "hy4"), ("minimax", "deepseek")]:
    a, b = M[ka], M[kb]
    d = a["mean"] - b["mean"]
    n = need_n(a["sd"], b["sd"], abs(d))
    cur = f"{a['n']}/{b['n']}轮"
    if n is None:
        print(f"{ka+' vs '+kb:<22}{cur:>10}{'∞':>8}{'—':>10}   分不开")
        continue
    extra = f"+{n - a['n']}/+{n - b['n']}"
    worth = "可接受" if n <= 8 else ("偏贵" if n <= 15 else "不划算")
    print(f"{ka+' vs '+kb:<22}{cur:>10}{n:>7}轮{extra:>10}   {worth}")

print()
print("=" * 84)
print("这个脚本的结论，以及它的局限")
print("=" * 84)
print()
print("1. 阈值法不随轮次收敛。阈值 = 2 × 单轮 sd 的最大值，与轮次 n 无关，")
print("   所以用它做梯队内排序，补多少轮都过不去。本次 deepseek 补到 4 轮，")
print("   阈值从 4.0pp 降到 3.2pp（因为 sd 估稳了），但 glm vs hy4 的 2.3pp")
print("   仍然在阈值内——这不是还差几轮的问题，是口径用错了。")
print()
print("2. 换 Welch t 之后，轮次少的那家会出假结果。看 glm vs minimax：")
print("   差 5.4pp、t 值 9.26 远大于常规临界 2，却因为 glm 只有 2 轮、")
print("   sd 估成 0.20pp，Welch 自由度塌到 1.1，临界值飙到 11.66，判成不可分。")
print("   n=2 的方差估计本身不可信（2 个样本算 sd，误差极大），")
print("   在这种样本量下做 t 检验是假精确，不能拿它当排序依据。")
print()
print("3. 所以本脚本只用来回答一个问题：靠补轮次能不能把梯队内排序做稳。")
print("   答案是：一对能，一对不能。")
for ka, kb in [("glm", "hy4"), ("minimax", "deepseek")]:
    a, b = M[ka], M[kb]
    d = abs(a["mean"] - b["mean"])
    n = need_n(a["sd"], b["sd"], d)
    extra = n - min(a["n"], b["n"])   # 按轮次少的那家算，它才是瓶颈
    tag = f"各补到 {n} 轮，还需 +{extra} 轮" + ("，便宜，值得跑" if extra <= 2
                                                else "，太贵，不划算")
    print(f"     {ka} vs {kb}（差 {d:.1f}pp）现 {a['n']}/{b['n']} 轮 → {tag}")
print()
print("4. 但上面这两个数建立在 n=2 的 sd 上，本身不可靠——glm 只有两轮、")
print("   两轮差 0.4pp，把 sd 估成 0.20pp，很可能低估了它真实的抖动。")
print("   所以补那一轮要当成一次判决，先定好规则再跑，不能跑完再解释：")
print("     glm 第 3 轮落在 60.5% 以上 → glm 第一坐实，与 hy4 的 2pp 差是真差")
print("     glm 第 3 轮掉到 59.0% 以下 → 与 hy4 差不足 1pp，判并列")
print()
print("5. 更根本的出路是换统计单位而不是加样本：见 rank_robust.py。")
