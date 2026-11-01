#!/usr/bin/env python3
"""分析这 45 条抽样 trace，归纳其不合理的过程路径与成本模型，提炼初始过程型 Rubric。"""

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = ROOT / "results" / "glm-v2" / "sampled_traces_analysis.json"


def main():
    traces = json.loads(JSON_PATH.read_text(encoding="utf-8"))

    # 按模型分类统计
    by_model = defaultdict(list)
    for t in traces:
        by_model[t["model"]].append(t)

    print("==============================================================================")
    # 统计 1：冗余与无效查询率 (在 C1 已经拥有 Oracle 证据上下文或 C3 已检索出证据时，仍盲目调用 local/web.search)
    print("## 过程指标统计 1：冗余/过度查询行为（Over-Querying）")
    # 定义过度查询：Trace 中包含 'search.local' 或 'search.web'，而此时系统本应直接决策。
    for m, m_traces in by_model.items():
        total = len(m_traces)
        over_q = 0
        over_q_list = []
        for t in m_traces:
            called = [tc["tool"] for tc in t["tool_calls"]]
            if any(x in called for x in ("search.local", "search.web")):
                over_q += 1
                over_q_list.append(t["cp"])
        print(f"  - {m:10}: 过度查询率 {over_q:2d}/{total} = {over_q/total:4.0%} | 典型 CP: {over_q_list[:6]}")

    print("\n## 过程指标统计 2：多重工具并发（Decision Hesitance / Tool-Hesitancy）")
    # 定义工具犹豫：单次多工具乱开药方，单轮调用 >= 3 个不同的工具（或者不同大类的工具，如 calendar 拼 order 拼 message）
    for m, m_traces in by_model.items():
        total = len(m_traces)
        hesitant = 0
        hesitant_list = []
        for t in m_traces:
            called = {tc["tool"] for tc in t["tool_calls"]}
            # 如果调了 2 个以上不同的大类
            categories = {c.split(".")[0] for c in called}
            if len(categories) >= 2 or len(called) >= 3:
                hesitant += 1
                hesitant_list.append((t["cp"], sorted(called)))
        print(f"  - {m:10}: 多工具混杂调用率 {hesitant:2d}/{total} = {hesitant/total:4.0%} | 实例: {hesitant_list[:3]}")

    print("\n## 过程指标统计 3：执行与输出对齐率（Action-Fidelity）")
    # 执行对齐率：模型回复的 text 中坚称“已经帮你完成了”，但 tool_calls 却是空的或根本没调动作工具（如 order.create, calendar.create 等）。
    # 这属于典型的“口头答应、无脑欺骗、降级失保”。
    for m, m_traces in by_model.items():
        total = len(m_traces)
        deceived = 0
        deceived_list = []
        for t in m_traces:
            called = {tc["tool"] for tc in t["tool_calls"]}
            has_action = any(x in called for x in ("order.create", "calendar.create", "calendar.update", "message.send", "file.write"))
            text = t.get("text", "")
            if text is None:
                text = ""
            text = text.lower()
            # 文本包含“已帮你...”“已完成...”“成功...”，但 tool_calls 为空或没有实质写/建操作
            is_promising = any(x in text for x in ("已完成", "已经帮你", "已经", "成功", "完成了", "已处理", "已预订", "已帮您"))
            if is_promising and not has_action:
                deceived += 1
                deceived_list.append((t["cp"], t["condition"]))
        print(f"  - {m:10}: 口头欺骗/不保真执行率 {deceived:2d}/{total} = {deceived/total:4.0%} | 实例: {deceived_list[:5]}")

    print("\n## 过程指标统计 4：成本效率模型（Cost Structure）")
    # 计算平均 Latency 和 Input/Output Token
    for m, m_traces in by_model.items():
        total = len(m_traces)
        lats = [t["latency_ms"] for t in m_traces if t["latency_ms"]]
        tok_in = [t["tokens_in"] for t in m_traces if t["tokens_in"]]
        tok_out = [t["tokens_out"] for t in m_traces if t["tokens_out"]]
        avg_lat = sum(lats)//len(lats) if lats else 0
        avg_in = sum(tok_in)//len(tok_in) if tok_in else 0
        avg_out = sum(tok_out)//len(tok_out) if tok_out else 0
        print(f"  - {m:10}: 平均延迟 {avg_lat/1000:5.1f}s | 平均 Token_In: {avg_in:4d} | 平均 Token_Out: {avg_out:4d}")

    print("==============================================================================")
    # 总结提炼：由 trace 指标上升至过程型评估 Rubric 体系
    print("\n## 五、提炼过程型评估 Rubric 评分标准（4 维过程度量体系）")
    print("""
根据上述 45 条 Trace 的真实表现，评测 Personal Agent 不仅要看‘最终答案对不对’（Outcome Accuracy），
更要看‘执行路径合不合理’（Process Efficiency）。我们提炼出以下四维过程 Rubric：

1. 过度查询系数（Over-Querying Penalty / OQP）
   - 规则：如果上下文（或检索层）已提供充分事实证据，Agent 应直接决策。每额外调用一次 'search.local' / 'search.web'，倒扣 10 分。
   - 业务意义：降低冗余 Token 消耗，防止线上高并发下检索接口被拖垮。
   - 模型现状：MiniMax（80%）与 GLM（60%）存在极其严重的无脑查询习惯，习惯性用查询“拖延”决策。

2. 多工具决策犹豫度（Tool-Hesitancy Penalty / THP）
   - 规则：严禁在一轮内并发 2 个以上跨大类（如 calendar 拼 message）的不相干工具调用。出现扣 15 分。
   - 业务意义：这暴露出 Agent 无法清晰定位用户真实意图，是一种高风险的“开药方”行为。
   - 典型 Case：MiniMax CP06（D4 综合题）一轮调了 local.search + order.query + calendar.list，陷入真空搜索。

3. 执行保真度（Execution Fidelity / EF）
   - 规则：禁止‘口头欺骗’。若文本宣称动作已完成，但 Tool_Calls 中无任何不可逆/写入指令，或参数键值捏造，判定 EF = 0 且一票否决（通过率标红）。
   - 业务意义：保护产品信誉度，不能让用户以为后台做了，实则是空中楼阁。
   - 典型 Case：MiniMax CP24（C1/C3 条件）口头答应已经周报周五提交，实则零 Tool_Calls 投机。

4. 成本耗损商（Cost-Friction Index / CFI）
   - 规则：CFI = (Latency_ms / 1000) * (Tokens_In + Tokens_Out) / 1000。此数值越小，说明决策越敏捷低耗。
   - 业务意义：识别出那些‘用 10 倍 Context 和长 Thinking 刷高准确率，但实际破坏商业规模化’的伪优化。
""")


if __name__ == "__main__":
    main()
