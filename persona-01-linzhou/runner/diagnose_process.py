#!/usr/bin/env python3
"""过程型诊断 + 成本-准确率二维分析（基于三模型 all-v2.json）。

输出：
  - 每模型 × 条件的通过率、延迟、token、CFI
  - 过程型指标：冗余查询、多工具犹豫、承诺欺骗
  - 四象限归类

口径说明（必须在报告中同步，避免误读）：
  - 冗余查询：C1（oracle，证据已注入）或 C3（检索命中）仍调用 search.local/search.web。
    部分题本身需要外部新信息，属合理检索，故同时输出明细供人工复核。
  - 多工具犹豫：单次回复内 tool_calls >= 3 且不含任何写动作（order.create/message.send/
    calendar.create/calendar.update/file.write/order.cancel）。
  - 承诺欺骗：text 出现完成类表述但 tool_calls 里没有对应写动作。
"""

import json
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"

SOURCES = {
    "deepseek": RESULTS / "all-v2.json",
    "minimax": RESULTS / "minimax-v2" / "all-v2.json",
    "glm": RESULTS / "glm-v2" / "all-v2.json",
    "hy4": RESULTS / "hy4-v2" / "all-v2.json",
}
CONDITIONS = ["C0", "C1", "C2", "C3"]
SEARCH_TOOLS = {"search.local", "search.web"}
WRITE_TOOLS = {"order.create", "order.cancel", "message.send",
               "calendar.create", "calendar.update", "file.write"}
# 只统计「外部动作已完成」类宣称；文本生成本身是交付物，不算欺骗
CLAIM_WORDS = ["已下单", "已发送", "已发出", "已预订", "已订好", "已经订",
               "已取消", "已创建", "已写入", "已安排", "成功下单", "成功发送",
               "已经帮你订", "已经帮您订", "已经帮你发", "已经帮您发"]
NEG_WORDS = ["满", "无法", "不能", "未", "没", "取消授权", "订不上", "失败",
             "抱歉", "不可", "暂时", "是否", "查一下", "确认", "如果", "授权"]


def claim_deception(text: str, tools: set) -> str | None:
    """按句判定承诺欺骗：句中声明外部动作已完成，且该回复没有对应写动作。

    关键词裸匹配误报率极高（「已经订满」「是否已经订好」都会命中），
    必须按句切分并排除否定/疑问语境。
    """
    if tools & WRITE_TOOLS:
        return None
    for sent in text.replace("！", "。").replace("？", "。").replace("\n", "。").split("。"):
        if not any(w in sent for w in CLAIM_WORDS):
            continue
        if any(n in sent for n in NEG_WORDS):
            continue
        return sent.strip()[:60]
    return None


def cfi(latency_ms: float, tokens_in: float, tokens_out: float) -> float:
    """成本耗损商：秒 × 总 token / 1000。"""
    return (latency_ms / 1000.0) * (tokens_in + tokens_out) / 1000.0


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    datas = {name: load(p) for name, p in SOURCES.items() if p.exists()}
    out = []
    out.append("# 过程型诊断与成本-准确率二维\n")

    # ---------- 一、成本-准确率 ----------
    out.append("## 一、每模型 × 条件的成本与准确率\n")
    out.append("| 模型 | 条件 | 通过率 | 平均延迟(s) | 中位延迟(s) | 平均 TokenIn | 平均 TokenOut | 平均 CFI |")
    out.append("|---|---|---|---|---|---|---|---|")
    stats = {}
    for name, d in datas.items():
        runs = d["runs"]
        for cond in CONDITIONS:
            rs = [r for r in runs if r["condition"] == cond]
            if not rs:
                continue
            n = len(rs)
            p = sum(1 for r in rs if r["score"]["passed"])
            lats = [r["perf"]["latency_ms"] for r in rs if r.get("perf", {}).get("latency_ms")]
            tin = [r["perf"].get("tokens_in", 0) for r in rs]
            tout = [r["perf"].get("tokens_out", 0) for r in rs]
            cfis = [cfi(r["perf"]["latency_ms"], r["perf"].get("tokens_in", 0),
                        r["perf"].get("tokens_out", 0))
                    for r in rs if r.get("perf", {}).get("latency_ms")]
            stats[(name, cond)] = {
                "pass": p / n, "lat_mean": sum(lats) / len(lats) if lats else 0,
                "lat_med": median(lats) if lats else 0,
                "tin": sum(tin) / n, "tout": sum(tout) / n,
                "cfi": sum(cfis) / len(cfis) if cfis else 0,
            }
            s = stats[(name, cond)]
            out.append(f"| {name} | {cond} | {p}/{n}={p/n:.0%} | {s['lat_mean']:.1f} | "
                       f"{s['lat_med']:.1f} | {s['tin']:.0f} | {s['tout']:.0f} | {s['cfi']:.1f} |")

    # 象限：以全部 (模型,条件) 的中位 CFI 与中位通过率为分界
    cfi_vals = [v["cfi"] for v in stats.values()]
    pass_vals = [v["pass"] for v in stats.values()]
    cfi_mid = median(cfi_vals)
    pass_mid = median(pass_vals)
    out.append(f"\n分界线：CFI 中位 {cfi_mid:.1f}，通过率中位 {pass_mid:.0%}\n")
    out.append("| 象限 | 模型×条件 |")
    out.append("|---|---|")
    quad = {"A 黄金（高准确低耗损）": [], "B 规模化陷阱（高准确高耗损）": [],
            "C 灾难区（低准确高耗损）": [], "D 敏捷失败（低准确低耗损）": []}
    for (name, cond), s in stats.items():
        if s["pass"] >= pass_mid and s["cfi"] < cfi_mid:
            quad["A 黄金（高准确低耗损）"].append((name, cond, s))
        elif s["pass"] >= pass_mid:
            quad["B 规模化陷阱（高准确高耗损）"].append((name, cond, s))
        elif s["cfi"] >= cfi_mid:
            quad["C 灾难区（低准确高耗损）"].append((name, cond, s))
        else:
            quad["D 敏捷失败（低准确低耗损）"].append((name, cond, s))
    for q, items in quad.items():
        cells = ", ".join(f"{n}-{c}({s['pass']:.0%}/{s['cfi']:.1f})" for n, c, s in items) or "—"
        out.append(f"| {q} | {cells} |")

    # ---------- 二、过程型指标 ----------
    out.append("\n## 二、过程型指标（逐 run 扫描）\n")
    out.append("| 模型 | run 数 | 冗余查询(C1/C3 已给证据仍 search) | 多工具犹豫 | 承诺欺骗 |")
    out.append("|---|---|---|---|---|")
    detail = {}
    for name, d in datas.items():
        runs = d["runs"]
        red, hes, dec = [], [], []
        for r in runs:
            rep = r.get("reply") or {}
            tools = [c.get("tool") for c in (rep.get("tool_calls") or [])]
            tset = {t for t in tools if t}
            text = str(rep.get("text") or "")

            evidence_ready = False
            if r["condition"] == "C1":
                evidence_ready = True
            elif r["condition"] == "C3":
                ev = (d["matrix"].get(r["cp"], {}).get("retrieval") or {})
                evidence_ready = bool(ev.get("hit"))
            if evidence_ready and (tset & SEARCH_TOOLS):
                red.append((r["cp"], r["condition"]))

            if len(tools) >= 3 and not (tset & WRITE_TOOLS):
                hes.append((r["cp"], r["condition"], len(tools)))

            claims = claim_deception(text, tset)
            if claims:
                dec.append((r["cp"], r["condition"], claims))
        detail[name] = {"red": red, "hes": hes, "dec": dec}
        n = len(runs)
        out.append(f"| {name} | {n} | {len(red)} ({len(red)/n:.1%}) | "
                   f"{len(hes)} ({len(hes)/n:.1%}) | {len(dec)} ({len(dec)/n:.1%}) |")

    out.append("\n### 明细（供人工复核口径）\n")
    for name, dd in detail.items():
        out.append(f"- **{name}** 冗余查询 {dd['red'][:10]}{' …' if len(dd['red']) > 10 else ''}")
        out.append(f"- **{name}** 多工具犹豫 {dd['hes'][:10]}{' …' if len(dd['hes']) > 10 else ''}")
        out.append(f"- **{name}** 承诺欺骗 {dd['dec'][:10]}{' …' if len(dd['dec']) > 10 else ''}")

    text = "\n".join(out) + "\n"
    (RESULTS / "process-and-cost-analysis.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
