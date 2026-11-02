#!/usr/bin/env python3
"""四条件上下文组装。

C0 无记忆：只给当前 session
C1 oracle：当前 session + 该检查点声明的证据 session
C2 全量上下文：截至当前 session 的全部历史，超预算按时间倒序截断
C3 完整 agent：由记忆后端检索相关 session（骨架用朴素检索代替）
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SESSIONS_FILE = ROOT / "data" / "sessions.json"
BIGRAM = None


def sid_index(sid: str) -> int:
    return int(sid[1:])


def estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / 1.6))


def find_turn(session: dict, trigger: str) -> int | None:
    """在 session 里定位触发话术属于第几轮（1 起）。找不到返回 None。"""
    for i, turn in enumerate(session["turns"], start=1):
        if turn == trigger or turn in trigger or trigger in turn:
            return i
    return None


def render_blocks(sessions: dict, ids: list[str], cutoff: tuple[str, int] | None = None) -> str:
    blocks = []
    for sid in ids:
        s = sessions[sid]
        turns = s["turns"]
        if cutoff and sid == cutoff[0]:
            turns = turns[: max(0, cutoff[1] - 1)]
        if not turns:
            continue
        lines = [f"【{sid}】{s['title']}"]
        lines += [f"用户：{t}" for t in turns]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def load_sessions(path: str | Path | None = None) -> dict:
    source = Path(path) if path is not None else SESSIONS_FILE
    return json.loads(source.read_text(encoding="utf-8"))["sessions"]


def build(cp: dict, condition: str, sessions: dict, memory=None,
          budget: int = 8000, trigger: str = "", turn: int | None = None) -> dict:
    """返回 {ids, text, tokens, truncated, policy, dropped, turn}。

    turn 是触发话术在当前 session 里的轮次（1 起）。给了 turn 就只渲染它之前的轮次，
    避免把同一 session 的后续对话当上下文，造成答案泄露。
    """
    cur = cp["session"]
    evidence = cp.get("evidence") or []
    dropped: list[str] = []

    if turn is None:
        turn = find_turn(sessions[cur], trigger)

    if condition == "C0":
        ids, policy = [cur], "current_only"
    elif condition == "C1":
        ids, policy = sorted({cur, *evidence}, key=sid_index), "oracle"
    elif condition == "C2":
        ids = [s for s in sorted(sessions, key=sid_index) if sid_index(s) <= sid_index(cur)]
        policy = "full_history_time_desc_truncate"
    elif condition == "C3":
        picked = memory.query(trigger, k=3, before=sid_index(cur)) if memory else []
        ids, policy = sorted({cur, *picked}, key=sid_index), "memory_backend"
    else:
        raise ValueError(f"未知条件：{condition}")

    text = render_blocks(sessions, ids, cutoff=(cur, turn) if turn else None)
    tokens = estimate_tokens(text)
    truncated = False

    if condition == "C2":
        # 保留当前 session，从最旧的开始丢，直到进预算
        keep = list(ids)
        while tokens > budget and len(keep) > 1:
            dropped.append(keep.pop(0))
            text = render_blocks(sessions, keep, cutoff=(cur, turn) if turn else None)
            tokens = estimate_tokens(text)
            truncated = True
        ids = keep

    return {
        "ids": ids,
        "text": text,
        "tokens": tokens,
        "truncated": truncated,
        "dropped": dropped,
        "policy": policy,
        "turn": turn,
    }


def build_messages(system: str, ctx: dict, trigger: str, reply_hint: str,
                   env: str = "") -> list[dict]:
    parts = [
        "以下是历史会话：",
        ctx["text"],
        "",
    ]
    if env:
        parts += ["当前环境状态（来自工具或系统，可直接采信）：", env, ""]
    parts += [f"当前消息：{trigger}", "", reply_hint]
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n".join(parts)},
    ]
