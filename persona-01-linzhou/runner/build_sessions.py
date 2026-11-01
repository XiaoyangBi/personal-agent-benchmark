#!/usr/bin/env python3
"""把 session 剧本 md 解析成结构化 JSON（只保留用户话术）。

用法：
    python3 build_sessions.py
输出：
    data/sessions.json
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sessions.json"

HEAD_RE = re.compile(r"^## (S\d{2})｜(.+)$", re.MULTILINE)
FILE_RE = re.compile(r"sessions-(S\d{2})")
TURN_RE = re.compile(r"^U(\d+)：(.*)$")
TAG_RE = re.compile(r"\s*\[[^\]]*\]")
CP_RE = re.compile(r"[（(][^（）()]*CP\d+[^（）()]*[）)]")  # 标题里的检查点编号不能进上下文


def clean(line: str) -> str:
    return TAG_RE.sub("", line).strip()


def clean_title(title: str) -> str:
    return CP_RE.sub("", title).strip()


def parse_file(path: Path) -> dict[str, dict]:
    text = path.read_text(encoding="utf-8")
    heads = list(HEAD_RE.finditer(text))
    result: dict[str, dict] = {}

    if not heads:
        m = FILE_RE.match(path.stem)
        if not m:
            return {}
        sid = m.group(1)
        result[sid] = {"title": path.stem, "turns": extract_turns(text)}
        return result

    for i, head in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        sid, title = head.group(1), clean_title(head.group(2).strip())
        body = text[head.end():end]
        result[sid] = {"title": title, "turns": extract_turns(body)}
    return result


def extract_turns(body: str) -> list[str]:
    turns = []
    for line in body.splitlines():
        m = TURN_RE.match(line.strip())
        if m:
            turns.append(clean(m.group(2)))
    return turns


def main() -> None:
    sessions: dict[str, dict] = {}
    for path in sorted(ROOT.glob("sessions-S*.md")):
        sessions.update(parse_file(path))

    ordered = {sid: sessions[sid] for sid in sorted(sessions)}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"persona_id": "persona-01-linzhou", "sessions": ordered},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"解析 {len(ordered)} 个 session：")
    for sid, s in ordered.items():
        chars = sum(len(t) for t in s["turns"])
        print(f"  {sid}  {len(s['turns']):>2} 轮  {chars:>5} 字  {s['title'][:28]}")


if __name__ == "__main__":
    main()
