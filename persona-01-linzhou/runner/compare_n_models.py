#!/usr/bin/env python3
"""N 个模型的横向评测对比（基于 all-v2.json 聚合文件）。

用法：
    python3 compare_n_models.py --inputs results/all-v2.json results/minimax-v2/all-v2.json ...

输出九个板块：四条件通过率、记忆增益、维度拆分、CP59-CP63 新题、
C1 失败模式、工具调用量、越权、否认历史率、延迟。
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

CONDITIONS = ["C0", "C1", "C2", "C3"]
NEW_CPS = ["CP59", "CP60", "CP61", "CP62", "CP63"]
ROOT = Path(__file__).resolve().parent.parent


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def short(model: str) -> str:
    return model.replace("-v4-flash", "").replace("-m3.1-flash", "").replace("-3.5-flash", "").replace("-5.3-flash", "")


def rates(data: dict, cps=None) -> dict:
    acc = defaultdict(lambda: [0, 0])
    for r in data["runs"]:
        if cps is not None and r["cp"] not in cps:
            continue
        c = r["condition"]
        acc[c][1] += 1
        if r["score"]["passed"]:
            acc[c][0] += 1
    return {c: (acc[c][0], acc[c][1]) for c in CONDITIONS if acc[c][1]}


def fmt_rate(x):
    p, t = x
    return f"{p}/{t}={p/t:.0%}" if t else "-"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", nargs="+", required=True)
    args = ap.parse_args()

    datas = []
    for p in args.inputs:
        d = load(p)
        datas.append((short(d["meta"].get("model", p)), d))
    names = [n for n, _ in datas]
    col = " | ".join(names)
    sep = "-" * 100

    print("=" * 100)
    print(f"N 模型横测：{col}")
    print("=" * 100)

    # 一、四条件通过率
    print("\n## 一、四条件通过率\n")
    print("| 条件 | " + " | ".join(names) + " |")
    print("|---|" + "---|" * len(names))
    for c in CONDITIONS:
        row = [fmt_rate(rates(d).get(c, (0, 0))) for _, d in datas]
        print(f"| {c} | " + " | ".join(row) + " |")
    # 总分
    row = []
    for _, d in datas:
        runs = d["runs"]
        p = sum(1 for r in runs if r["score"]["passed"])
        row.append(f"{p}/{len(runs)}={p/len(runs):.0%}")
    print(f"| 总计 | " + " | ".join(row) + " |")

    # 二、记忆增益 C3-C0 / C1-C0
    print("\n## 二、记忆增益（百分点）\n")
    print("| 模型 | C3−C0 | C1−C0 | C2−C0 |")
    print("|---|---|---|---|")
    for n, d in datas:
        r = rates(d)
        line = [f"{(r[c][0]/r[c][1] - r['C0'][0]/r['C0'][1])*100:+.1f}pp" for c in ("C3", "C1", "C2")]
        print(f"| {n} | " + " | ".join(line) + " |")

    # 三、维度拆分（D1-D7，C0 vs C1 vs C3）
    print("\n## 三、维度拆分（通过率 C0/C1/C3）\n")
    dims = sorted({r["dim"] for _, d in datas for r in d["runs"]})
    print("| 维度 | " + " | ".join(names) + " |")
    print("|---|" + "---|" * len(names))
    for dim in dims:
        row = []
        for _, d in datas:
            acc = defaultdict(lambda: [0, 0])
            for r in d["runs"]:
                if r["dim"] != dim or r["condition"] not in ("C0", "C1", "C3"):
                    continue
                acc[r["condition"]][1] += 1
                if r["score"]["passed"]:
                    acc[r["condition"]][0] += 1
            row.append("/".join(f"{acc[c][0]/acc[c][1]:.0%}" if acc[c][1] else "-" for c in ("C0", "C1", "C3")))
        print(f"| {dim} | " + " | ".join(row) + " |")

    # 四、CP59-CP63 新题
    print("\n## 四、P0-1 新题（CP59-CP63）四条件表现\n")
    new_set = set(NEW_CPS)
    print("| 检查点 | " + " | ".join(f"{n} C0/C1/C2/C3" for n in names) + " |")
    print("|---|" + "---|" * len(names))
    for cid in NEW_CPS:
        row = []
        for _, d in datas:
            m = d["matrix"].get(cid, {})
            cells = []
            for c in CONDITIONS:
                e = m.get(c)
                if e is None:
                    cells.append("-")
                elif e.get("error") or (e.get("text") in ("", None) and not e.get("tool_calls")):
                    cells.append("∅")  # 空回复/读取失败
                else:
                    cells.append("✓" if e["passed"] else "✕")
            row.append("/".join(cells))
        print(f"| {cid} | " + " | ".join(row) + " |")

    # 五、C1 失败模式
    print("\n## 五、C1 失败模式（oracle 给证据仍失败）\n")
    print("| 模型 | " + " | ".join(names) + " |")
    print("|---|" + "---|" * len(names))
    all_modes = set()
    mode_counts = []
    for _, d in datas:
        cnt = Counter()
        for cid, cprow in d["matrix"].items():
            e = cprow.get("C1")
            if e and not e["passed"]:
                m = (cprow.get("attribution") or {}).get("c1_failure", {}).get("mode", "") or "未分类"
                cnt[m] += 1
        mode_counts.append(cnt)
        all_modes |= set(cnt)
    for mode in sorted(all_modes):
        print(f"| {mode} | " + " | ".join(str(mc.get(mode, 0)) for mc in mode_counts) + " |")
    tot = [sum(mc.values()) for mc in mode_counts]
    print(f"| 合计 | " + " | ".join(str(t) for t in tot) + " |")

    # 六、工具调用量
    print("\n## 六、工具调用量（全部条件合计，前 6）\n")
    for n, d in datas:
        cnt = Counter()
        for cid, cprow in d["matrix"].items():
            for c in CONDITIONS:
                for call in (cprow.get(c, {}).get("tool_calls") or []):
                    cnt[call.get("tool")] += 1
        top = ", ".join(f"{k}={v}" for k, v in cnt.most_common(6))
        print(f"{n}: 共 {sum(cnt.values())} | {top}")

    # 七、越权（断言口径：只认 tool_not_called 显式禁令）
    # 不能用工具名粗筛：CP19/CP20/CP30 的 expects.action=true，写动作是预期行为。
    banned = {}
    spec_file = ROOT / "data" / "assertions.json"
    if spec_file.exists():
        spec = json.loads(spec_file.read_text(encoding="utf-8"))
        spec = spec.get("checkpoints") or spec
        for cid, s in spec.items():
            for rule in s.get("rules", []):
                if rule.get("type") == "tool_not_called" and rule.get("tool"):
                    banned.setdefault(cid, set()).add(rule["tool"])

    print("\n## 七、越权题（断言口径：该题显式禁止该工具，模型仍调用）\n")
    for n, d in datas:
        hits = []
        for cid, tools in sorted(banned.items(), key=lambda x: int(x[0][2:])):
            for c in CONDITIONS:
                called = {tc.get("tool") for tc in (d["matrix"].get(cid, {}).get(c, {}).get("tool_calls") or [])}
                if called & tools:
                    hits.append(f"{cid}.{c}")
        print(f"{n} ({len(hits)}): {hits}")

    # 八、否认历史率
    print("\n## 八、否认历史率（deny_rate）\n")
    print("| 模型 | C0 | C1 | C2 | C3 |")
    print("|---|---|---|---|---|")
    for n, d in datas:
        dr = (d.get("stats") or {}).get("deny_rate", {})
        print(f"| {n} | " + " | ".join(f"{dr.get(c, 0):.1%}" for c in CONDITIONS) + " |")

    # 九、延迟
    print("\n## 九、延迟（ms）\n")
    for n, d in datas:
        lats = sorted(r["perf"]["latency_ms"] for r in d["runs"] if r.get("perf", {}).get("latency_ms"))
        if lats:
            print(f"{n}: 平均 {sum(lats)//len(lats)} | 中位 {lats[len(lats)//2]} | 最大 {lats[-1]}")

    # 十、检索命中
    print("\n## 十、C3 检索命中\n")
    for n, d in datas:
        tot = hit = 0
        for cid, cprow in d["matrix"].items():
            if "retrieval" in cprow:
                tot += 1
                if (cprow["retrieval"] or {}).get("hit", cprow.get("attribution", {}).get("retrieval_hit")):
                    hit += 1
        if tot:
            print(f"{n}: {hit}/{tot} = {hit/tot:.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
