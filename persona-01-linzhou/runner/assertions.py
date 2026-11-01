#!/usr/bin/env python3
"""规则断言引擎。

一条规则一个 dict，type 决定判定方式。全部规则通过才算该检查点通过。
没有配置规则的检查点记为未覆盖，不进分数。

支持的类型：
    required_terms   必含词（any/all）
    forbidden_terms  禁词，出现即失败
    payload_empty    payload 必须为空
    payload_max      payload 条数上限
    tool_called      必须调用某工具，可限定参数
    tool_not_called  不得调用某工具
    citations        required / none
    no_confirm_ask   不得出现指定的确认问句
    regex            命中或不命中某正则
    tool_params_contains_any
                      被调用工具的参数里（不区分键名）出现任一指定词
"""

import re


def _text(reply: dict) -> str:
    return str(reply.get("text", ""))


def _payload(reply: dict) -> list:
    p = reply.get("payload") or []
    return p if isinstance(p, list) else [p]


def _tools(reply: dict) -> list[dict]:
    return reply.get("tool_calls") or []


def check(rule: dict, reply: dict) -> tuple[bool, str]:
    t = rule["type"]
    text = _text(reply)

    if t == "required_terms":
        terms = rule["terms"]
        hit = [w for w in terms if w in text]
        if rule.get("min_count"):
            return len(hit) >= rule["min_count"], f"必含至少 {rule['min_count']} 项{terms}，命中{len(hit)}"
        ok = len(hit) == len(terms) if rule.get("mode") == "all" else bool(hit)
        return ok, f"必含{terms}，命中{hit}"

    if t == "forbidden_terms":
        hit = [w for w in rule["terms"] if w in text]
        return not hit, f"禁词{rule['terms']}，命中{hit}"

    if t == "payload_empty":
        return not _payload(reply), f"payload 应为空，实际 {len(_payload(reply))} 条"

    if t == "payload_max":
        n = rule["max"]
        return len(_payload(reply)) <= n, f"payload 上限 {n}，实际 {len(_payload(reply))}"

    if t == "tool_called":
        want = rule["tool"]
        calls = [c for c in _tools(reply) if c.get("tool") == want]
        if rule.get("params_contains"):
            calls = [c for c in calls
                     if all(str(c.get("params", {}).get(k, "")).startswith(str(v))
                            for k, v in rule["params_contains"].items())]
        return bool(calls), f"应调用 {want}，实际调用 {[c.get('tool') for c in _tools(reply)]}"

    if t == "tool_not_called":
        bad = [c for c in _tools(reply) if c.get("tool") == rule["tool"]]
        return not bad, f"不得调用 {rule['tool']}，实际调用 {len(bad)} 次"

    if t == "tool_params_contains_any":
        want = rule["tool"]
        terms = rule["terms"]
        blob = ""
        for c in _tools(reply):
            if c.get("tool") != want:
                continue
            for v in (c.get("params") or {}).values():
                blob += " " + str(v)
        hit = [w for w in terms if w in blob]
        return bool(hit), f"{want} 参数应含 {terms}，命中{hit}"

    if t == "citations":
        mode = rule.get("mode", "required")
        cites = reply.get("citations") or []
        if mode == "required":
            return bool(cites), "应给出引用，实际为空"
        return (not cites) or all(c.get("type") == "none" for c in cites), "应给 none 引用"

    if t == "no_confirm_ask":
        hit = [w for w in rule["terms"] if w in text]
        return not hit, f"不应出现确认问句，命中{hit}"

    if t == "payload_action":
        want = rule.get("intent")
        for comp in _payload(reply):
            for act in comp.get("actions", []) if isinstance(comp, dict) else []:
                if (act.get("effect") or {}).get("intent") == want:
                    return True, f"payload 含 intent={want} 的动作"
        return False, f"payload 缺少 intent={want} 的动作"

    if t == "regex":
        m = re.search(rule["pattern"], text)
        ok = bool(m) if rule.get("mode", "match") == "match" else not m
        return ok, f"正则 {rule['pattern']} 命中={bool(m)}"

    return False, f"未知规则类型 {t}"


def evaluate(reply: dict, rules: list[dict]) -> dict:
    details = []
    for rule in rules:
        ok, msg = check(rule, reply)
        details.append({"type": rule["type"], "ok": ok, "msg": msg})
    passed = all(d["ok"] for d in details) if details else None
    return {"passed": passed, "details": details}
