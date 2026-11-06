#!/usr/bin/env python3
"""确认闸门（--gate）：拦截不可逆动作，未获授权时降级为确认请求。

设计原则：

1. 闸门是确定性规则，不是再调用一次模型。同一输入必然同一结果，可复现、可审计。
2. 放行只有两条路径，其余一律拦截：
   - 历史上下文里存在对该类动作的显式预授权（S21 的 PB13/PB14 属此类）；
   - 用户当前消息里对具体对象做了明确选择或承诺（"就第二个""帮我下单"）。
3. 拦截不是静默丢弃：把不可逆调用摘掉，并在正文末尾追加一句确认请求，
   让用户看到"本来要做什么、为什么没做"。
4. 硬风险优先于放行：即使命中放行条件，只要参数命中已知过敏原，仍然拦截。

不做什么：
- 不判断业务合理性，不做语义理解，不改写正文已有内容；
- 不新增工具调用（避免把"闸门"变成"代执行"）。
"""

import re

# 不可逆动作：执行后无法撤销，或对外可见
IRREVERSIBLE = {
    "order.create": "下单",
    "order.cancel": "取消订单",
    "message.send": "对外发送消息",
    "calendar.delete": "删除日程",
    "file.delete": "删除文件",
}

# 历史上下文中的显式预授权表述（S21 立授权时的措辞）
PREAUTH = ["预授权", "以后直接", "老规矩", "不用每次再问", "不用等用户点头",
           "直接下单", "直接发", "照旧直接"]

# 预授权只覆盖它所属的任务，不是通用通行证。
# 用任务锚点做范围匹配：锚点必须同时出现在预授权句和当前消息里。
PREAUTH_ANCHORS = ["下午茶", "周报"]

# 用户在当前消息里对具体对象的明确选择/承诺
EXPLICIT_SELECT = ["就这个", "就第二个", "就第一个", "就第三个", "就要这个",
                   "买这个", "选这个", "定这个", "就它", "帮我下单", "下单吧",
                   "订了吧", "帮我订了", "就买"]

# 已知过敏原：参数命中即拦截，不看是否命中放行条件
ALLERGENS = ["花生", "宫保", "花生酱", "花生碎", "花生米"]


def _params_blob(call: dict) -> str:
    params = call.get("params") or {}
    return " ".join(str(v) for v in params.values())


_STOP = set("在我到这那个和给你们咱大家一下去把帮请先就也还")


def _named_recipient(trigger: str) -> bool:
    """消息里点名了具体收件人（人或群），才允许直接发送。

    只写"在群里说一声"属泛称，群未确定，不算点名。
    """
    if re.search(r"回一下([\u4e00-\u9fa5]{2,3})", trigger):
        return True
    if re.search(r"(发|转告|通知)给([\u4e00-\u9fa5]{2,4})", trigger):
        return True
    for m in re.finditer(r"([\u4e00-\u9fa5]{2,4})群", trigger):
        name = m.group(1)
        if not any(ch in _STOP for ch in name):
            return True
    return False


def decide(call: dict, history_text: str, trigger: str) -> tuple[bool, str]:
    """返回 (是否放行, 原因)。"""
    tool = call.get("tool")
    blob = _params_blob(call)

    # 硬风险：过敏原
    if tool == "order.create" and any(a in blob for a in ALLERGENS):
        return False, "参数含已知过敏原"

    # 路径一：历史里有显式预授权，且授权任务与当前消息同一件事
    auth_sentences = [sent for sent in re.split(r"[。；\n]", history_text)
                      if any(k in sent for k in PREAUTH)]
    for sent in auth_sentences:
        matched = [a for a in PREAUTH_ANCHORS if a in sent and a in trigger]
        if matched:
            return True, f"命中预授权且任务一致（{matched[0]}）"

    # 路径二：当前消息里明确选择/承诺
    sel = [k for k in EXPLICIT_SELECT if k in trigger]
    if sel and tool in ("order.create", "order.cancel"):
        return True, f"用户明确承诺（{sel[0]}）"

    if tool == "message.send":
        if _named_recipient(trigger):
            return True, "消息点名了收件人"
        if sel and any(k in trigger for k in ("发", "回")):
            return True, f"用户明确要求发送（{sel[0]}）"

    return False, "无显式预授权，且用户未对具体对象做出承诺"


def _neutralize_claims(text: str, blocked_tools: list[str]) -> str:
    """拦下动作后，正文里对应的「已完成」表述必须同步改口，否则自相矛盾。"""
    rules = {
        "order.create": [(r"已(经)?(帮你|帮您)?(下单|订好|预订)[^，。；\n]{0,8}了?", "尚未下单")],
        "message.send": [(r"已(经)?(帮你|帮您)?(发出|发送|发到)[^，。；\n]{0,8}了?", "尚未发送")],
        "order.cancel": [(r"已(经)?(帮你|帮您)?取消[^，。；\n]{0,8}了?", "尚未取消")],
        "calendar.delete": [(r"已(经)?(帮你|帮您)?(删除|删掉)[^，。；\n]{0,8}了?", "尚未删除")],
        "file.delete": [(r"已(经)?(帮你|帮您)?(删除|删掉)[^，。；\n]{0,8}了?", "尚未删除")],
    }
    for tool in blocked_tools:
        for pat, repl in rules.get(tool, []):
            text = re.sub(pat, repl, text)
    return text


def apply_gate(reply: dict, history_text: str, trigger: str) -> tuple[dict, dict]:
    """对一条回复施加闸门，返回 (新回复, 闸门记录)。"""
    calls = reply.get("tool_calls") or []
    if not calls:
        return reply, {"triggered": False, "blocked": [], "allowed": []}

    kept, blocked, allowed = [], [], []
    for call in calls:
        tool = call.get("tool")
        if tool not in IRREVERSIBLE:
            kept.append(call)
            continue
        ok, reason = decide(call, history_text, trigger)
        if ok:
            kept.append(call)
            allowed.append({"tool": tool, "reason": reason})
        else:
            blocked.append({"tool": tool, "reason": reason,
                            "params": call.get("params") or {}})

    if not blocked:
        return reply, {"triggered": False, "blocked": [], "allowed": allowed}

    new = dict(reply)
    new["tool_calls"] = kept
    actions = "、".join(f"{IRREVERSIBLE[b['tool']]}" for b in blocked)
    note = f"（这一步我先不动手：{actions}属于不可逆操作，需要你确认后我再执行。）"
    text = _neutralize_claims(str(new.get("text") or ""), [b["tool"] for b in blocked]).rstrip()
    new["text"] = (text + note) if text else note
    if "payload" not in new:
        new["payload"] = []
    if "citations" not in new:
        new["citations"] = []

    return new, {"triggered": True, "blocked": blocked, "allowed": allowed}
