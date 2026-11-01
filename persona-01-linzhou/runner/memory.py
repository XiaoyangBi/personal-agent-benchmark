#!/usr/bin/env python3
"""C3 的记忆后端接口与朴素基线。

接口只有两个方法：
    insert(session_id, text, index)   顺序写入
    query(question, k, before)        取相关 session

骨架实现用字符二元组重合度排序，不依赖任何外部服务。
后续接真实记忆系统时，只要实现同样两个方法即可替换。
"""

import re
from collections import Counter

CJK_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")


def bigrams(text: str) -> Counter:
    chars = CJK_RE.findall(text)
    return Counter("".join(chars[i:i + 2]) for i in range(len(chars) - 1))


class NaiveMemory:
    def __init__(self):
        self.store: dict[str, dict] = {}

    def insert(self, session_id: str, text: str, index: int) -> None:
        self.store[session_id] = {"text": text, "index": index, "grams": bigrams(text)}

    def query(self, question: str, k: int = 3, before: int | None = None) -> list[str]:
        q = bigrams(question or "")
        scored = []
        for sid, item in self.store.items():
            if before is not None and item["index"] >= before:
                continue
            overlap = sum(min(c, q[g]) for g, c in item["grams"].items() if g in q)
            if overlap:
                scored.append((overlap / (sum(q.values()) + 1), sid))
        scored.sort(reverse=True)
        return [sid for _, sid in scored[:k]]
