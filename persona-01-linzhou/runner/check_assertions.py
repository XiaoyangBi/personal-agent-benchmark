#!/usr/bin/env python3
"""断言文件检查器。

检查 data/assertions.json 是否与检查点、剧本对得上：
1. 58 个检查点是否都有断言
2. 规则类型是否合法、必填字段是否齐全
3. turn 是否在 session 轮次数范围内
4. evidence 是否都是合法 session
5. trigger 是否为空、是否能在对应 session 里找到
6. 是否存在只有空规则列表的检查点

用法：
    python3 check_assertions.py
退出码：0 通过，1 有错误。
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

RULE_FIELDS = {
    "required_terms": ["terms"],
    "forbidden_terms": ["terms"],
    "payload_empty": [],
    "payload_max": ["max"],
    "tool_called": ["tool"],
    "tool_not_called": ["tool"],
    "citations": [],
    "no_confirm_ask": ["terms"],
    "regex": ["pattern"],
    "payload_action": ["intent"],
    "tool_params_contains_any": ["tool", "terms"],
}

TOOLS = {
    "calendar.create", "calendar.update", "calendar.delete", "calendar.list",
    "order.create", "order.cancel", "order.query",
    "message.draft", "message.send",
    "file.read", "file.write", "file.delete",
    "search.local", "search.web",
}
INTENTS = {"edit"}

errors, warnings = [], []


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def main() -> int:
    persona = json.loads((DATA / "persona-01.json").read_text(encoding="utf-8"))
    assertions = json.loads((DATA / "assertions.json").read_text(encoding="utf-8"))
    sessions = json.loads((DATA / "sessions.json").read_text(encoding="utf-8"))["sessions"]

    cp_map = {c["id"]: c for c in persona["checkpoints"]}
    missing = sorted(set(cp_map) - set(assertions))
    extra = sorted(set(assertions) - set(cp_map))
    if missing:
        err(f"缺断言的检查点：{missing}")
    if extra:
        err(f"多出未定义的检查点：{extra}")

    total_rules = 0
    for cid, spec in assertions.items():
        sid = cp_map.get(cid, {}).get("session")
        rules = spec.get("rules") or []
        total_rules += len(rules)

        if not spec.get("trigger"):
            err(f"{cid} trigger 为空")
        if not rules:
            err(f"{cid} 没有任何规则")
        if sid and sid not in sessions:
            err(f"{cid} 对应 session {sid} 不存在")
            continue

        turn = spec.get("turn")
        if not isinstance(turn, int) or turn < 1:
            err(f"{cid} turn 非法：{turn}")
        elif turn > max(1, len(sessions[sid]["turns"])):
            err(f"{cid} turn={turn} 超出 {sid} 的轮次数 {len(sessions[sid]['turns'])}")

        for ev in spec.get("evidence", []):
            if ev not in sessions:
                err(f"{cid} evidence 含非法 session：{ev}")

        found = any(spec["trigger"] in t or t in spec["trigger"] for t in sessions[sid]["turns"])
        if not found:
            warn(f"{cid} 的触发话术在 {sid} 剧本里找不到")

        for i, rule in enumerate(rules):
            t = rule.get("type")
            if t not in RULE_FIELDS:
                err(f"{cid} 第 {i + 1} 条规则类型非法：{t}")
                continue
            for field in RULE_FIELDS[t]:
                if field not in rule or rule[field] in ("", None, []):
                    err(f"{cid} 第 {i + 1} 条规则缺字段 {field}")
            if t in ("required_terms", "forbidden_terms", "no_confirm_ask", "tool_params_contains_any"):
                terms = rule.get("terms")
                if not isinstance(terms, list) or not terms:
                    err(f"{cid} 第 {i + 1} 条规则 terms 非法")
                elif len(terms) != len(set(terms)):
                    warn(f"{cid} 第 {i + 1} 条规则 terms 有重复")
            if t in ("tool_called", "tool_not_called", "tool_params_contains_any") and rule.get("tool") not in TOOLS:
                err(f"{cid} 第 {i + 1} 条规则工具名不在清单里：{rule.get('tool')}")
            if t == "payload_action" and rule.get("intent") not in INTENTS:
                err(f"{cid} 第 {i + 1} 条规则 intent 非法：{rule.get('intent')}")
            if t == "regex":
                try:
                    re.compile(rule.get("pattern", ""))
                except re.error as exc:
                    err(f"{cid} 第 {i + 1} 条正则编译失败：{exc}")
            if t == "payload_max" and not isinstance(rule.get("max"), int):
                err(f"{cid} 第 {i + 1} 条 payload_max 不是整数")

        need = {w for r in rules if r.get("type") == "required_terms" for w in r.get("terms", [])}
        ban = {w for r in rules if r.get("type") == "forbidden_terms" for w in r.get("terms", [])}
        conflict = need & ban
        if conflict:
            err(f"{cid} 同一条断言里既要求又禁止：{sorted(conflict)}")

    print("=" * 52)
    print("断言检查报告")
    print("=" * 52)
    print(f"检查点 {len(cp_map)}，有断言 {len(assertions)}，规则 {total_rules} 条")
    dims = Counter(str(cp_map[cid]["dim"]).split("/")[0] for cid in assertions if cid in cp_map)
    print("维度覆盖：" + "，".join(f"{d} {n}" for d, n in sorted(dims.items())))
    kinds = Counter(r.get("type") for s in assertions.values() for r in s.get("rules", []))
    print("规则类型：" + "，".join(f"{k} {n}" for k, n in kinds.most_common()))
    if errors:
        print(f"错误 {len(errors)} 条")
        for e in errors:
            print(f"  [错误] {e}")
    if warnings:
        print(f"警告 {len(warnings)} 条")
        for w in warnings:
            print(f"  [警告] {w}")
    if not errors and not warnings:
        print("全部通过")
    print("结论：" + ("不通过" if errors else "通过"))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
