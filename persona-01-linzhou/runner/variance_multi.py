#!/usr/bin/env python3
"""多模型方差对比：同一 spec 下，各模型跑过的每一轮分别重放，看梯队是否站得住。

单轮分数做排序是不够的——两个模型差 2pp，可能只是采样噪声。本脚本把每个模型
跑过的所有轮次都列出来，给出均值、标准差、极差，再按噪声阈值做两两比较，
直接回答"谁和谁能分开、谁和谁分不开"。

用法：
    python3 variance_multi.py --spec ../data/assertions-v3.json \
        --model deepseek=../results/all-v2.json,../results/rep2-deepseek.json \
        --model minimax=../results/minimax-v2/all-v2.json,../results/rep2-minimax.json \
        --model hy4=../results/hy4-v2/results-v2-full-hy4b.json,...
"""

import argparse
import json
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import assertions as A  # noqa: E402
import stats_util as S  # noqa: E402

CONDITIONS = ["C0", "C1", "C2", "C3"]


def ok_keys(runs, want=None):
    """本轮里成功（无 error）且在题集内的 (cp, cond) 集合。"""
    ks = set()
    for r in runs:
        if (r.get("reply") or {}).get("error"):
            continue
        if want and r["cp"] not in want:
            continue
        ks.add((r["cp"], r["condition"]))
    return ks


def score_runs(runs, spec, want=None, valid=None):
    """按 spec 重放，返回 (整体通过数, 分条件通过数 dict, 断言通过数, 断言总数)

    valid 给出时只统计这些 (cp, cond)——用于网关错误导致各轮样本不齐时，
    取各轮的交集，保证跨轮比较是配对的，不会用错误条目稀释噪声。
    """
    tot = 0
    per_cond = {c: 0 for c in CONDITIONS}
    per_cond_n = {c: 0 for c in CONDITIONS}
    a_ok = a_tot = 0
    for r in runs:
        reply = r.get("reply") or {}
        if reply.get("error"):
            continue
        if want and r["cp"] not in want:
            continue
        if valid is not None and (r["cp"], r["condition"]) not in valid:
            continue
        rules = (spec.get(r["cp"]) or {}).get("rules") or []
        sc = A.evaluate(reply, rules) if rules else (r.get("score") or {})
        details = sc.get("details") or []
        ok = sum(1 for d in details if d.get("ok"))
        a_ok += ok
        a_tot += len(details)
        p = bool(sc.get("passed"))
        tot += p
        per_cond[r["condition"]] += p
        per_cond_n[r["condition"]] += 1
    return tot, per_cond, per_cond_n, a_ok, a_tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--model", action="append", required=True,
                    help="模型名=run文件1,run文件2,... 可重复")
    ap.add_argument("--threshold", type=float, default=0.0,
                    help="可信阈值（pp），0 表示用实测最大标准差推算")
    ap.add_argument("--cps", default="",
                    help="只看这些题，逗号分隔；空=全部。用于子集噪声估计")
    args = ap.parse_args()
    want = {x.strip() for x in args.cps.split(",") if x.strip()}

    spec = json.loads(Path(args.spec).read_text())
    print(f"重放 spec：{Path(args.spec).name}"
          + (f"   题集：{len(want)} 题（子集）" if want else "   题集：全部")
          + "\n")

    # 先收集所有模型所有轮次的原始数据
    pending = []
    for m in args.model:
        name, files = m.split("=", 1)
        raw = []
        for f in files.split(","):
            p = Path(f)
            if not p.exists():
                print(f"  跳过（文件不存在）：{f}")
                continue
            d = json.loads(p.read_text())
            raw.append((p, d))
        if raw:
            pending.append((name, raw))

    # 全局交集：跨模型比较必须建立在完全相同的条目集上，
    # 否则各家分母不同，分数不可比（网关错误会随机让某家少几条）
    gvalid = None
    for _, raw in pending:
        for _, d in raw:
            ks = ok_keys(d["runs"], want)
            gvalid = ks if gvalid is None else (gvalid & ks)
    if gvalid is not None:
        per_model_max = {}
        for name, raw in pending:
            per_model_max[name] = max(len(ok_keys(d["runs"], want)) for _, d in raw)
        dropped = {k: v - len(gvalid) for k, v in per_model_max.items()}
        print(f"  全局交集 {len(gvalid)} 条"
              + "（各家丢弃：" + "、".join(f"{k} {v}" for k, v in dropped.items() if v) + "）"
              if any(dropped.values()) else f"  全局交集 {len(gvalid)} 条（无丢弃）")

    models = {}
    for name, raw in pending:
        rounds = []
        valid = gvalid
        for p, d in raw:
            tot, pc, pcn, a_ok, a_tot = score_runs(d["runs"], spec, want, valid)
            n = len(valid)
            rounds.append({"file": p.name, "run_id": d["meta"].get("run_id"),
                           "pass": tot, "n": n, "pct": tot / n if n else 0,
                           "per_cond": pc, "per_cond_n": pcn,
                           "a_ok": a_ok, "a_tot": a_tot})
        models[name] = rounds

    # 每个模型的轮次汇总
    print("=" * 76)
    print("1. 各模型逐轮分数")
    print("=" * 76)
    summary = {}
    for name, rounds in models.items():
        pcts = [r["pct"] for r in rounds]
        mean = st.fmean(pcts)
        # 用样本标准差（ddof=1）而不是总体标准差：我们是在用几轮去估"单轮抖动有多大"，
        # 这是抽样估计，不是把这几轮当总体。n=2 时两者差 1.41 倍，用总体标准差会
        # 系统性低估噪声，阈值随之偏窄。
        sd = st.stdev(pcts) if len(pcts) > 1 else None
        rng = (max(pcts) - min(pcts)) if len(pcts) > 1 else 0
        se = (sd / (len(pcts) ** 0.5)) if sd is not None else None
        summary[name] = {"mean": mean, "sd": sd, "rng": rng, "n_round": len(pcts),
                         "pcts": pcts, "rounds": rounds, "se": se,
                         "lo": min(pcts), "hi": max(pcts)}
        cells = "  ".join(f"{p*100:.1f}%" for p in pcts)
        sd_s = f"{sd*100:.2f}pp" if sd is not None else "—（仅一轮）"
        se_s = f"{se*100:.2f}pp" if se is not None else "—"
        print(f"  {name:<12}轮次 {len(pcts)}  逐轮 {cells}   均值 {mean*100:.1f}%   "
              f"标准差 {sd_s}  标准误 {se_s}  区间 [{min(pcts)*100:.1f}, {max(pcts)*100:.1f}]")

    # 噪声阈值
    sds = [v["sd"] for v in summary.values() if v["sd"] is not None]
    if args.threshold:
        thr = args.threshold / 100
        thr_src = "指定"
    elif sds:
        thr = 2 * max(sds)
        thr_src = f"实测最大标准差 {max(sds)*100:.2f}pp × 2"
    else:
        thr = 0.03
        thr_src = "兜底 3pp（无多轮数据）"
    print(f"\n  可信阈值 {thr*100:.1f}pp（{thr_src}）")

    # 两两比较
    print()
    print("=" * 76)
    print("2. 两两比较：谁和谁能分开")
    print("=" * 76)
    order = sorted(summary, key=lambda k: -summary[k]["mean"])
    print(f"  {'对比':<22}{'均值差':>8}{'阈值法':>9}{'配对Welch':>10}{'p':>8}   观测区间法")
    for i in range(len(order)):
        for j in range(i + 1, len(order)):
            a, b = order[i], order[j]
            sa, sb = summary[a], summary[b]
            diff = sa["mean"] - sb["mean"]
            verdict = "可分" if diff > thr else "不可分"
            # 配对 Welch：用这一对自身的标准误，而不是全局阈值
            d, se, t, df, p = S.welch(sa["mean"], sa["sd"], sa["n_round"],
                                     sb["mean"], sb["sd"], sb["n_round"])
            wv = "可分" if p < 0.05 else "不可分"
            # 区间法：两家的观测区间是否重叠。不重叠说明领先在已观测的每一轮里都成立
            sep = sa["lo"] > sb["hi"]
            if sep:
                iv = f"区间不重叠（{sa['lo']*100:.1f}% > {sb['hi']*100:.1f}%）"
            else:
                iv = f"区间重叠（[{sa['lo']*100:.1f},{sa['hi']*100:.1f}] vs [{sb['lo']*100:.1f},{sb['hi']*100:.1f}]）"
            print(f"  {a+' vs '+b:<22}{diff*100:>7.1f}pp{verdict:>9}{wv:>10}"
                  f"{p:>8.3f}   {iv}")

    print("\n  阈值法取噪声最大的那家当基准，偏保守——当比较的一对不含那家时会被压回不可分；")
    print("  配对 Welch 用这一对自身的标准误，随轮次收敛；区间法只看已观测轮次，偏乐观。")
    print("  两者都说可分，结论最硬；两者不一致，说明证据不足，需补轮次。")

    # 梯队
    print()
    print("=" * 76)
    print("3. 梯队划分")
    print("=" * 76)
    # 与梯队首名比较，不用相邻差——避免 A≈B 且 B≈C 时把 A、C 也并进同一档的链式问题
    tiers, cur = [], [order[0]]
    for k in order[1:]:
        if summary[cur[0]]["mean"] - summary[k]["mean"] > thr:
            tiers.append(cur)
            cur = [k]
        else:
            cur.append(k)
    tiers.append(cur)
    for i, t in enumerate(tiers, 1):
        names = "、".join(t)
        pcts = " / ".join(f"{summary[x]['mean']*100:.1f}%" for x in t)
        print(f"  第 {i} 梯队：{names}（{pcts}）")
    if len(tiers) == 1:
        print("\n  全部并列，当前判据下无法区分模型。")
    else:
        print(f"\n  共 {len(tiers)} 个梯队，梯队间差异超过阈值，梯队内部视为并列。")

    # 不可分链提示：A≈B 且 B≈C 但 A≠C，说明阈值下这批分数只能分档不能全序
    chain = []
    for i in range(len(order) - 2):
        a, b, c = order[i], order[i + 1], order[i + 2]
        dab = summary[a]["mean"] - summary[b]["mean"]
        dbc = summary[b]["mean"] - summary[c]["mean"]
        dac = summary[a]["mean"] - summary[c]["mean"]
        if dab <= thr and dbc <= thr and dac > thr:
            chain.append(f"{a}≈{b}≈{c}，但 {a} 与 {c} 相差 {dac*100:.1f}pp 可分")
    if chain:
        print("\n  存在不可分链，只能分档、不能全序：")
        for c in chain:
            print(f"    {c}")

    # 单轮排序的稳定性
    print()
    print("=" * 76)
    print("4. 若只用单轮，排序会怎么变")
    print("=" * 76)
    multi = {k: v for k, v in summary.items() if v["n_round"] > 1}
    if multi:
        # 用所有轮次，不只取最少的轮次——各家轮次不同（deepseek 4 / minimax 4 /
        # hy4 3 / glm 2），只看前 n 轮会丢掉大部分信息。某轮缺某家时该家不参与该轮排序。
        maxr = max(v["n_round"] for v in multi.values())
        orders = {}
        for i in range(maxr):
            part = {k: v for k, v in multi.items() if i < v["n_round"]}
            if len(part) < 2:
                continue
            snap = sorted(part, key=lambda k: -part[k]["pcts"][i])
            key = " > ".join(snap)
            orders.setdefault(key, []).append(i + 1)
        for o, rs in sorted(orders.items(), key=lambda x: -len(x[1])):
            print(f"  {len(rs)}/{maxr} 轮出现（第 {','.join(map(str, rs))} 轮）：{o}")
        if len(orders) == 1:
            print("  单轮排序稳定。")
        else:
            print(f"  单轮排序不稳定，共出现 {len(orders)} 种顺序。")
    else:
        print("  只有单轮数据，无法判断。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
