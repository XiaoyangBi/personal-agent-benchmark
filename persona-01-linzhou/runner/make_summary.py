#!/usr/bin/env python3
"""从 all.json 生成一份可读的 Markdown 报告。

用法：
    python3 make_summary.py
输出：
    results/summary.md
"""

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"

ABNORMAL = {"记忆污染", "检索未命中", "读取失败", "能力失败", "记忆生效·oracle异常", "废题"}


def main() -> None:
    data = json.loads((RESULTS / "all.json").read_text(encoding="utf-8"))
    matrix, stats, meta = data["matrix"], data.get("stats", {}), data["meta"]

    cond_pass = Counter()
    for row in matrix.values():
        for c in ("C0", "C1", "C2", "C3"):
            if c in row and row[c]["passed"]:
                cond_pass[c] += 1
    n = len(matrix)

    lines = [
        "# Personal Agent 评测报告 v1",
        "",
        f"- 评测对象：{meta['persona']}",
        f"- 模型：{meta.get('model', '')}",
        f"- 覆盖：{n} / {meta['coverage']['total']} 个检查点，四条件共 {len(data['runs'])} 次运行",
        f"- 合并自 {len(set(stats.get('sources', {}).values()))} 次运行",
        "",
        "## 一、总体",
        "",
        "| 条件 | 通过 | 通过率 | 说明 |",
        "|---|---|---|---|",
        f"| C0 无记忆 | {cond_pass['C0']} | {cond_pass['C0'] / n:.0%} | 下界 |",
        f"| C1 oracle | {cond_pass['C1']} | {cond_pass['C1'] / n:.0%} | 排除检索变量 |",
        f"| C2 全量上下文 | {cond_pass['C2']} | {cond_pass['C2'] / n:.0%} | 硬塞历史 |",
        f"| C3 完整 agent | {cond_pass['C3']} | {cond_pass['C3'] / n:.0%} | 被测结果 |",
        "",
        f"- 异常题（按归因标签）：{stats.get('abnormal_label')} / {n} = {stats.get('abnormal_label_ratio', 0):.0%}",
        f"- 异常题（含 C0 越权）：{stats.get('abnormal_union')} / {n} = {stats.get('abnormal_union_ratio', 0):.0%}",
        f"- C0 越权：{', '.join(stats.get('c0_violation') or []) or '无'}",
        f"- C1 失败：{len(stats.get('c1_fail') or [])} 题，模式 {stats.get('c1_fail_modes') or '无'}",
        "",
        "## 二、判读矩阵",
        "",
        "| 检查点 | C0 | C1 | C2 | C3 | 归因 | 检索命中 | C1 失败模式 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for cid, row in matrix.items():
        a = row.get("attribution") or {}
        cells = " | ".join("✓" if row[c]["passed"] else "✕" for c in ("C0", "C1", "C2", "C3"))
        lines.append(
            f"| {cid} | {cells} | {a.get('label', '')} | "
            f"{'✓' if a.get('retrieval_hit') else '✕'} | {a.get('c1_failure', {}).get('mode', '') or '—'} |"
        )

    lines += ["", "## 三、C1 失败原因", "", "| 检查点 | 行为模式 | 失败类别 | 具体失败项 |", "|---|---|---|---|"]
    for cid, row in matrix.items():
        a = row.get("attribution") or {}
        if "C1" in row and not row["C1"]["passed"]:
            f = a.get("c1_failure") or {}
            lines.append(
                f"| {cid} | {f.get('mode', '')} | {', '.join(f.get('categories', []))} | "
                f"{'; '.join(f.get('details', [])[:2])} |"
            )

    lines += ["", "## 四、标签分布", "", "| 标签 | 题数 | 性质 |", "|---|---|---|"]
    for k, v in sorted(stats.get("labels", {}).items(), key=lambda x: -x[1]):
        lines.append(f"| {k} | {v} | {'异常' if k in ABNORMAL else '正常'} |")

    lines += [
        "", "## 五、已知限制", "",
        "1. 单题单次运行，方差未估计，单题结论只能当线索",
        "2. 判分以词表与工具调用断言为主，语义类判断是弱代理",
        f"3. 仅覆盖 {n} / {meta['coverage']['total']} 个检查点，未跑部分不计分",
        "4. 模型输出受 harness 提示影响，换 harness 需重跑基线",
    ]

    out = RESULTS / "summary.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"报告写入 {out}")


if __name__ == "__main__":
    main()
