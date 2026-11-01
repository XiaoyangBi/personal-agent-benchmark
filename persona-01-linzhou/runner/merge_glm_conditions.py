#!/usr/bin/env python3
"""GLM 分段补跑的条件级合并：对每个 (检查点, 条件) 取 run_id 最新的非错误 run。

背景：网关间歇超时导致 CP 粒度重跑多轮后，CP22 等题在每轮文件中
仍至少有一个条件是 TimeoutError。逐条件挑最优来源组装完整 row。

用法：
    python3 merge_glm_conditions.py

输出：
    results/glm-v2/results-v2-glm-merged-src.json （mode=api，供 aggregate.py 消费）
"""

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "results"
OUT_DIR = SRC / "glm-v2"

FILES = [
    "results-v2-full-glm.json",
    "results-v2-glm-retry.json",
    "results-v2-glm-retry2.json",
    "results-v2-glm-retry3.json",
    "results-v2-glm-retry4.json",
]
CONDITIONS = ["C0", "C1", "C2", "C3"]


def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)
    datas = []
    for name in FILES:
        p = SRC / name
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        datas.append((d["meta"]["run_id"], d))
    datas.sort(key=lambda x: x[0])

    # 每个 (cp, cond) 收集候选：所有文件中的 entry（run_id 升序，后者覆盖前者）
    best: dict[tuple[str, str], tuple[str, dict, dict]] = {}  # (cp,cond) -> (run_id, entry, file_data)
    for run_id, d in datas:
        for r in d.get("runs", []):
            if (r.get("reply") or {}).get("error"):
                continue  # 错误 run 永不入选
            key = (r["cp"], r["condition"])
            best[key] = (run_id, r, d)

    cps = sorted({cp for cp, _ in best}, key=lambda x: int(x[2:]))
    matrix, runs = {}, []
    incomplete = []
    for cp in cps:
        row = {}
        ok = True
        for cond in CONDITIONS:
            hit = best.get((cp, cond))
            if hit is None:
                ok = False
                break
            _, r, _ = hit
            row[cond] = {
                "passed": r["score"]["passed"],
                "details": r["score"]["details"],
                "text": (r.get("reply") or {}).get("text", ""),
                "tool_calls": (r.get("reply") or {}).get("tool_calls", []),
                "context": r.get("context", {}),
            }
        if not ok:
            incomplete.append(cp)
            continue
        # retrieval 与 attribution 的原始输入取该 CP 最新来源文件中的 retrieval
        newest_run_id = max(best[(cp, c)][0] for c in CONDITIONS)
        src_data = next(d for rid, d in datas if rid == newest_run_id)
        row["retrieval"] = (src_data["matrix"].get(cp) or {}).get("retrieval")
        matrix[cp] = row
        for cond in CONDITIONS:
            runs.append(best[(cp, cond)][1])

    out = {
        "meta": {
            "persona": "persona-01-linzhou",
            "mode": "api",  # aggregate.py 只吃 mode=api 的原始结果
            "model": "glm-5.3-flash",
            "budget": 8000,
            "conditions": CONDITIONS,
            "budget_note": "condition-level merge of 5 segment files",
            "run_id": "merged-cond-20261028-1200-fglm",
            "coverage": {"with_rules": len(matrix), "total": 63},
            "workers": 4,
        },
        "runs": runs,
        "matrix": matrix,
        "stats": {},
    }
    out_path = OUT_DIR / "results-v2-glm-merged-src.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"CP 覆盖 {len(matrix)}/63 | runs {len(runs)}/252 | 不完整: {incomplete}")
    print(f"条件来源分布: {Counter(best[(cp,c)][0][:15] for cp in cps for c in CONDITIONS if (cp,c) in best)}")
    print(f"写入 {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
