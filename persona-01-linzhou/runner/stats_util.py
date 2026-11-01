#!/usr/bin/env python3
"""统计工具：Welch t 检验与配对比较。

为什么不用全局阈值判可分：
全局阈值 = 2 × 所有模型里最大的 sd，是一个刻意保守的单一门槛。当比较的一对
不包含那个噪声最大的模型时，这个门槛会把本可分开的对比也压回"不可分"
（本轮 hy4 vs minimax 就是这样被压住的）。配对比较该用这一对自身的标准误。

t 分布的 p 值用正则化不完全贝塔函数算（Numerical Recipes 的连分式实现）。
"""

import math


def _betacf(a, b, x):
    """连分式展开，计算不完全贝塔函数（Numerical Recipes）。"""
    MAXIT, EPS, FPMIN = 200, 3e-16, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < EPS:
            break
    return h


def betainc(a, b, x):
    """正则化不完全贝塔函数 I_x(a, b)。"""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(lbeta + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - math.exp(lbeta + b * math.log(1.0 - x)
                          + a * math.log(x)) * _betacf(b, a, 1.0 - x) / b


def t_cdf(t, df):
    """t 分布累积分布。"""
    if df <= 0:
        return float("nan")
    x = df / (df + t * t)
    p = 0.5 * betainc(df / 2.0, 0.5, x)
    return 1.0 - p if t > 0 else p


def welch(ma, sa, na, mb, sb, nb):
    """两样本 Welch t 检验，返回 (均值差, se, t, df, 双侧 p)。"""
    va, vb = sa * sa, sb * sb
    se = math.sqrt(va / na + vb / nb)
    d = ma - mb
    if se == 0:
        return d, 0.0, float("inf"), float("inf"), 0.0
    t = d / se
    num = (va / na + vb / nb) ** 2
    den = (va / na) ** 2 / max(na - 1, 1) + (vb / nb) ** 2 / max(nb - 1, 1)
    df = num / den if den else float("inf")
    p = 2.0 * (1.0 - t_cdf(abs(t), df)) if df != float("inf") else \
        2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(t) / math.sqrt(2))))
    return d, se, t, df, min(1.0, p)


def binom_two_sided(k, n):
    """精确二项检验（p=0.5）双侧 p 值。"""
    if n == 0:
        return 1.0
    pmf = [math.comb(n, i) * 0.5 ** n for i in range(n + 1)]
    obs = pmf[k]
    return min(1.0, sum(p for p in pmf if p <= obs + 1e-12))
