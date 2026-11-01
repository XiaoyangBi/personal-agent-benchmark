#!/usr/bin/env python3
"""提取并分析代表性 Trace，用于提炼过程型 Rubric（评分标准）和成本分析。

抽取规则：
- DeepSeek, MiniMax, GLM 每家抽取 15 条（合计 45 条）
- 优先选择：C1 失败、C3 越权
- 记录关键路径：意图、检索命中、工具调用、最终输出、Latency、Token
"""

import json
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "results"

MODELS = {
    "deepseek": RESULTS_DIR / "all-v2.json",
    "minimax": RESULTS_DIR / "minimax-v2" / "all-v2.json",
    "glm": RESULTS_DIR / "glm-v2" / "all-v2.json"
}


def analyze_runs():
    all_traces = []
    
    for mname, path in MODELS.items():
        if not path.exists():
            print(f"警告: {path} 不存在")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        runs = data.get("runs", [])
        matrix = data.get("matrix", {})
        
        # 挑选：1. C1 失败；2. C3 越权 (即 C3 调用了不可逆动作且未通过或处于敏感检查点)
        c1_fails = [r for r in runs if r["condition"] == "C1" and not r["score"]["passed"]]
        c3_runs = [r for r in runs if r["condition"] == "C3"]
        
        # 筛选典型的 C3 越权
        c3_violations = []
        for r in c3_runs:
            calls = (r.get("reply") or {}).get("tool_calls") or []
            has_irreversible = any(c.get("tool") in ("order.create", "message.send", "file.delete") for c in calls)
            if has_irreversible:
                c3_violations.append(r)
                
        # 混洗并挑选前 15 条 (7 条 C1 失败，8 条 C3 越权，如果不够则用其他凑)
        chosen = []
        chosen.extend(c1_fails[:8])
        chosen.extend(c3_violations[:8])
        
        # 补足 15 条
        if len(chosen) < 15:
            remaining = [r for r in runs if r not in chosen]
            chosen.extend(remaining[:(15 - len(chosen))])
            
        for r in chosen[:15]:
            cp_id = r["cp"]
            cond = r["condition"]
            cp_meta = matrix.get(cp_id, {})
            attr = cp_meta.get("attribution", {})
            retrieval = cp_meta.get("retrieval", {})
            
            reply = r.get("reply") or {}
            score = r.get("score") or {}
            perf = r.get("perf") or {}
            
            trace_view = {
                "model": mname,
                "cp": cp_id,
                "condition": cond,
                "dim": r.get("dim", ""),
                "attribution_label": attr.get("label", "未归因"),
                "retrieval_hit": retrieval.get("hit", False),
                "retrieval_info": retrieval,
                "latency_ms": perf.get("latency_ms", 0),
                "tokens_in": perf.get("tokens_in", 0),
                "tokens_out": perf.get("tokens_out", 0),
                "tool_calls": reply.get("tool_calls", []),
                "reply_text": reply.get("text", "")[:120],
                "score_passed": score.get("passed", False),
                "score_details": score.get("details", [])
            }
            all_traces.append(trace_view)
            
    print(f"成功提取了 {len(all_traces)} 条样本 Trace。")
    return all_traces


def summarize_findings(traces):
    print("\n--- Trace 过程性特征分析（PM 视角）---")
    
    # 1. 冗余工具调用分析
    redundant_cases = []
    over_query_cases = []
    long_latency_cases = []
    
    for t in traces:
        calls = t["tool_calls"]
        lat = t["latency_ms"]
        text = t["reply_text"]
        
        # 特征 A：本该直接回答却进行冗余查询（以工具查询代替回答）
        if t["condition"] == "C1" and not t["score_passed"] and t["attribution_label"] == "能力失败":
            # 检查是否有查询
            has_query = any("list" in c.get("tool","") or "query" in c.get("tool","") or "search" in c.get("tool","") for c in calls)
            if has_query:
                over_query_cases.append(t)
                
        # 特征 B：单轮多次冗余调用同一工具
        tools_called = [c.get("tool") for c in calls]
        if len(tools_called) != len(set(tools_called)) and len(tools_called) > 1:
            redundant_cases.append(t)
            
        # 特征 C：单次调用 Latency 偏高（>30s）
        if lat > 30000:
            long_latency_cases.append(t)
            
    print(f"1. 冗余工具调用/多次重复调用同一工具: {len(redundant_cases)} / {len(traces)}")
    for t in redundant_cases[:3]:
        print(f"   [{t['model']} - {t['cp']} - {t['condition']}] 工具序列: {[c.get('tool') for c in t['tool_calls']]}")
        
    print(f"2. C1 条件下‘以查询代替回答’的典型 Trace 占比: {len(over_query_cases)} / {len(traces)}")
    for t in over_query_cases[:3]:
        print(f"   [{t['model']} - {t['cp']}] 最终回复: {t['reply_text']} | 工具: {[c.get('tool') for c in t['tool_calls']]}")
        
    print(f"3. 慢阻滞调用 (Latency > 30s): {len(long_latency_cases)} / {len(traces)}")
    for t in long_latency_cases[:3]:
        print(f"   [{t['model']} - {t['cp']} - {t['condition']}] 耗时: {t['latency_ms']/1000:.1f}s | Token In: {t['tokens_in']} | Out: {t['tokens_out']}")

    # 导出到文件
    out_path = RESULTS_DIR / "glm-v2" / "sampled_traces_analysis.json"
    out_path.write_text(json.dumps(traces, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n全量 {len(traces)} 条 trace 的详细明细已导出到 {out_path}")


if __name__ == "__main__":
    traces = analyze_runs()
    summarize_findings(traces)
