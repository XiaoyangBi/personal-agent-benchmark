#!/usr/bin/env python3
"""把 results.json 渲染成一页 HTML 汇总。

用法：
    python3 report.py
输出：
    results/report.html
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
COND_LABEL = {"C0": "C0 无记忆", "C1": "C1 oracle", "C2": "C2 全量上下文", "C3": "C3 完整 agent"}
ATTR_COLOR = {
    "有效记忆": "ok",
    "记忆失败": "warn",
    "读取失败": "warn",
    "检索未命中": "warn",
    "能力失败": "bad",
    "记忆污染": "bad",
    "废题": "muted",
    "陷阱题·C0不适用": "muted",
    "非记忆题": "muted",
}

CSS = """
:root{--bg:#f4f3ef;--card:#fffdf9;--line:#e4dfd2;--ink:#1f2328;--muted:#6b7280;
--green:#07C160;--red:#DC2626;--amber:#B45309;--soft:#eeeadf}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font-family:-apple-system,"PingFang SC","Helvetica Neue",Arial,sans-serif;font-size:14px;line-height:1.6}
.wrap{max-width:1100px;margin:0 auto;padding:36px 24px 64px}
h1{font-size:24px;margin:0 0 6px;font-weight:600}
.sub{color:var(--muted);font-size:13px}
.chips{margin:14px 0 26px;display:flex;gap:8px;flex-wrap:wrap}
.chip{background:var(--soft);border:1px solid var(--line);border-radius:999px;
padding:3px 11px;font-size:12px;color:#4b5563}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:26px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.card .k{font-size:12px;color:var(--muted)}
.card .v{font-size:26px;font-weight:600;margin-top:2px}
.card .n{font-size:12px;color:var(--muted)}
section{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:20px 22px;margin-bottom:18px}
h2{font-size:15px;margin:0 0 14px;font-weight:600}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:middle}
th{font-size:12px;color:var(--muted);font-weight:500}
td.c,th.c{text-align:center;width:74px}
.pass{color:var(--green);font-weight:600}
.fail{color:var(--red);font-weight:600}
.na{color:#c3bcae}
.tag{font-size:12px;padding:2px 8px;border-radius:6px;border:1px solid var(--line);
display:inline-block;margin:2px 4px 2px 0}
.tag.ok{color:#067a3d;background:#eafaf1;border-color:#bfe9d1}
.tag.warn{color:var(--amber);background:#fdf3e3;border-color:#f1d9b5}
.tag.bad{color:var(--red);background:#fdeceb;border-color:#f3c9c6}
.tag.muted{color:#6b7280;background:#f2efe7}
.bars{display:grid;grid-template-columns:110px 1fr 52px;gap:8px 12px;align-items:center}
.bar{height:8px;background:var(--soft);border-radius:99px;overflow:hidden}
.bar span{display:block;height:100%;background:var(--green)}
.bar span.low{background:var(--red)}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}
.fail-list{display:grid;gap:10px}
.fail-item{border-left:3px solid var(--red);padding:6px 12px;background:#fdfaf7}
.fail-item .m{color:var(--muted);font-size:12px}
footer{color:var(--muted);font-size:12px;margin-top:24px}
"""


def pct(a: int, b: int) -> int:
    return round(100 * a / b) if b else 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(RESULTS / "results.json"))
    ap.add_argument("--out", default=str(RESULTS / "report.html"))
    args = ap.parse_args()

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    runs, matrix, meta = data["runs"], data["matrix"], data["meta"]
    stats = data.get("stats") or {}

    total = meta["coverage"]["total"]
    covered = meta["coverage"]["with_rules"]
    passed = sum(1 for r in runs if r["score"]["passed"])
    miss = sum(1 for row in matrix.values()
               if (row.get("attribution") or {}).get("retrieval_hit") is False)
    pollution = sum(1 for row in matrix.values()
                    if (row.get("attribution") or {}).get("label") == "记忆污染")
    violate = sum(1 for row in matrix.values()
                  if (row.get("attribution") or {}).get("c0_violation"))

    dims = defaultdict(lambda: {"pass": 0, "all": 0})
    for r in runs:
        d = str(r["dim"]).split("/")[0]
        dims[d]["all"] += 1
        dims[d]["pass"] += 1 if r["score"]["passed"] else 0

    cost = defaultdict(lambda: {"tokens": [], "trunc": 0, "lat": []})
    for r in runs:
        c = cost[r["condition"]]
        c["tokens"].append(r["context"]["tokens"])
        c["trunc"] += 1 if r["context"]["truncated"] else 0
        c["lat"].append(r["perf"]["latency_ms"])

    rows = []
    for cid, row in matrix.items():
        cells = []
        for cond in ("C0", "C1", "C2", "C3"):
            if cond not in row:
                cells.append('<td class="c na">—</td>')
                continue
            ok = row[cond]["passed"]
            cells.append(f'<td class="c {"pass" if ok else "fail"}">{"✓" if ok else "✕"}</td>')
        a = row.get("attribution") or {}
        tags = [f"<span class='tag {ATTR_COLOR.get(a.get('label'), 'muted')}'>{a.get('label', '')}</span>"]
        if a.get("retrieval_hit") is False:
            tags.append("<span class='tag warn'>检索未命中</span>")
        if a.get("c2_conflict"):
            tags.append("<span class='tag warn'>C2 干扰</span>")
        if a.get("c2_tool_diff"):
            tags.append("<span class='tag muted'>C2 动作不同</span>")
        if a.get("c0_violation"):
            tags.append(f"<span class='tag bad'>C0 越权：{', '.join(a['c0_violation'])}</span>")
        if a.get("tool_diff_c1_c3"):
            tags.append("<span class='tag muted'>C1/C3 工具不同</span>")
        rows.append(
            f"<tr><td class='mono'>{cid}</td><td>{row.get('session', '')}</td>"
            f"{''.join(cells)}<td>{''.join(tags)}</td>"
            f"<td class='mono'>{a.get('c2_text_sim', '')}</td></tr>"
        )

    dim_rows = []
    for d in sorted(dims):
        v = dims[d]
        p = pct(v["pass"], v["all"])
        cls = "low" if p < 50 else ""
        dim_rows.append(
            f"<div>{d}</div><div class='bar'><span class='{cls}' style='width:{p}%'></span></div>"
            f"<div class='mono'>{p}%</div>"
        )

    cost_rows = []
    for cond in ("C0", "C1", "C2", "C3"):
        if cond not in cost:
            continue
        c = cost[cond]
        avg = int(sum(c["tokens"]) / len(c["tokens"])) if c["tokens"] else 0
        lat = int(sum(c["lat"]) / len(c["lat"])) if c["lat"] else 0
        cost_rows.append(
            f"<tr><td>{COND_LABEL[cond]}</td><td class='mono'>{avg:,}</td>"
            f"<td class='mono'>{c['trunc']}</td><td class='mono'>{lat:,} ms</td></tr>"
        )

    ret_rows = []
    for cid, row in matrix.items():
        r = row.get("retrieval") or {}
        if not r:
            continue
        hit = "✓" if r.get("hit") else "✕"
        cls = "pass" if r.get("hit") else "fail"
        ret_rows.append(
            f"<tr><td class='mono'>{cid}</td><td>{', '.join(r.get('evidence', [])) or '—'}</td>"
            f"<td>{', '.join(r.get('retrieved', [])) or '—'}</td>"
            f"<td class='c {cls}'>{hit}</td>"
            f"<td class='mono'>{', '.join(r.get('missing', [])) or '—'}</td></tr>"
        )

    tool_rows = []
    for cid, row in matrix.items():
        a = row.get("attribution") or {}
        if not (a.get("c0_violation") or a.get("tool_diff_c1_c3")):
            continue
        tool_rows.append(
            f"<tr><td class='mono'>{cid}</td>"
            f"<td>{', '.join(a.get('c0_violation') or []) or '—'}</td>"
            f"<td class='mono'>{', '.join(a.get('c1_tools') or []) or '—'}</td>"
            f"<td class='mono'>{', '.join(a.get('c3_tools') or []) or '—'}</td>"
            f"<td>{'不同' if a.get('tool_diff_c1_c3') else '一致'}</td></tr>"
        )

    c1_rows = []
    for cid, row in matrix.items():
        a = row.get("attribution") or {}
        if "C1" not in row or row["C1"]["passed"]:
            continue
        f = a.get("c1_failure") or {}
        c1_rows.append(
            f"<tr><td class='mono'>{cid}</td>"
            f"<td>{row.get('session', '')}</td>"
            f"<td>{f.get('mode', '') or '—'}</td>"
            f"<td>{', '.join(f.get('categories', [])) or '—'}</td>"
            f"<td class='m'>{'; '.join(f.get('details', [])[:2]) or '—'}</td></tr>"
        )

    fails = []
    for r in runs:
        if r["score"]["passed"]:
            continue
        bad = [d for d in r["score"]["details"] if not d["ok"]]
        if not bad:
            continue
        fails.append(
            f"<div class='fail-item'><strong>{r['cp']} · {COND_LABEL[r['condition']]}</strong>"
            f"<div class='m'>{str(r['reply'].get('text', ''))[:140]}</div>"
            f"<div class='m'>失败项：{'; '.join(d['msg'] for d in bad)}</div></div>"
        )

    abnormal_block = ""
    if stats:
        labels = stats.get("labels", {})
        label_rows = "".join(
            f"<tr><td>{k}</td><td class='mono'>{v}</td>"
            f"<td>{'题目待修' if k == '废题' else ('异常' if k in ('记忆污染','检索未命中','读取失败','能力失败','记忆生效·oracle异常') else '正常')}</td></tr>"
            for k, v in sorted(labels.items(), key=lambda x: -x[1])
        )
        modes = "，".join(f"{k} {v}" for k, v in (stats.get("c1_fail_modes") or {}).items()) or "无"
        abnormal_block = f"""
<section><h2>异常汇总</h2>
<table><thead><tr><th>指标</th><th>数值</th><th>口径</th></tr></thead><tbody>
<tr><td>已评测检查点</td><td class='mono'>{stats.get('checkpoints', len(matrix))}</td><td>按最新一次运行去重</td></tr>
<tr><td>异常题（按标签）</td><td class='mono'>{stats.get('abnormal_label', 0)}</td><td>占比 {stats.get('abnormal_label_ratio', 0):.0%}</td></tr>
<tr><td>异常题（含 C0 越权）</td><td class='mono'>{stats.get('abnormal_union', 0)}</td><td>占比 {stats.get('abnormal_union_ratio', 0):.0%}</td></tr>
<tr><td>C0 越权题</td><td class='mono'>{', '.join(stats.get('c0_violation') or []) or '无'}</td><td>无记忆条件下调用不可逆工具</td></tr>
<tr><td>C1 失败题</td><td class='mono'>{len(stats.get('c1_fail') or [])}</td><td>行为模式：{modes}</td></tr>
<tr><td>题目待修（废题）</td><td class='mono'>{', '.join(stats.get('design_issue') or []) or '无'}</td><td>无记忆也能过，题目不区分记忆</td></tr>
<tr><td>陷阱未触发</td><td class='mono'>{len(stats.get('trap_missed') or [])} / {stats.get('trap_total', 0)}</td><td>{', '.join(stats.get('trap_missed') or []) or '全部触发过'}</td></tr>
</tbody></table>
<h2 style="margin-top:20px">标签分布</h2>
<table><thead><tr><th>归因标签</th><th>题数</th><th>性质</th></tr></thead>
<tbody>{label_rows}</tbody></table></section>"""

    html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Personal Agent 评测结果 · {meta['run_id']}</title>
<style>{CSS}</style></head><body><div class="wrap">
<h1>Personal Agent 评测结果</h1>
<div class="sub">{meta['persona']} · 运行 {meta['run_id']} · 模式 {meta['mode']} · 模型 {meta['model']}</div>
<div class="chips">
  <span class="chip">条件 {' / '.join(meta['conditions'])}</span>
  <span class="chip">上下文预算 {meta['budget']:,} tokens</span>
  <span class="chip">检查点覆盖 {covered} / {total}</span>
</div>

<div class="cards">
  <div class="card"><div class="k">运行总次数</div><div class="v">{len(runs)}</div>
    <div class="n">检查点 × 条件</div></div>
  <div class="card"><div class="k">断言通过</div><div class="v">{passed}</div>
    <div class="n">{pct(passed, len(runs))}%</div></div>
  <div class="card"><div class="k">检索未命中</div><div class="v">{miss}</div>
    <div class="n">证据会话没被召回</div></div>
  <div class="card"><div class="k">记忆污染 / C0 越权</div><div class="v">{pollution} / {violate}</div>
    <div class="n">无记忆能过却更差 / 无记忆直接越权</div></div>
</div>

{abnormal_block}

<section><h2>判读矩阵</h2>
<table><thead><tr><th>检查点</th><th>来源</th><th class="c">C0</th><th class="c">C1</th>
<th class="c">C2</th><th class="c">C3</th><th>归因</th><th>C2 与 C1 文本相似度</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></section>

<section><h2>C3 检索明细</h2>
<table><thead><tr><th>检查点</th><th>证据会话</th><th>实际检索</th><th class="c">命中</th><th>缺失</th></tr></thead>
<tbody>{''.join(ret_rows)}</tbody></table></section>

<section><h2>C1 失败原因</h2>
<table><thead><tr><th>检查点</th><th>来源</th><th>行为模式</th><th>失败类别</th><th>具体失败项</th></tr></thead>
<tbody>{''.join(c1_rows) or '<tr><td colspan="5" class="sub">本次 C1 全部通过</td></tr>'}</tbody></table></section>

<section><h2>工具与越权明细</h2>
<table><thead><tr><th>检查点</th><th>C0 越权工具</th><th>C1 工具</th><th>C3 工具</th><th>C1/C3 差异</th></tr></thead>
<tbody>{''.join(tool_rows) or '<tr><td colspan="5" class="sub">本次没有越权或工具差异</td></tr>'}</tbody></table></section>

<section><h2>按维度通过率</h2><div class="bars">{''.join(dim_rows)}</div></section>

<section><h2>上下文成本</h2>
<table><thead><tr><th>条件</th><th>平均上下文 tokens</th><th>截断次数</th><th>平均延迟</th></tr></thead>
<tbody>{''.join(cost_rows)}</tbody></table></section>

<section><h2>失败明细</h2><div class="fail-list">{''.join(fails) or '<div class="sub">本次运行没有失败项</div>'}</div></section>

<footer>生成于 {meta['run_id']} · 断言覆盖 {covered} / {total} 个检查点，未覆盖题目不计分</footer>
</div></body></html>"""

    out = Path(args.out)
    out.write_text(html, encoding="utf-8")
    print(f"报告写入 {out}")


if __name__ == "__main__":
    main()
