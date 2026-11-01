#!/usr/bin/env python3
"""Generate public navigation and explicit trace-availability metadata."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "persona-01-linzhou" / "data"
DOCS = ROOT / "docs"


def checkpoint_index() -> None:
    persona = json.loads((DATA / "persona-01.json").read_text(encoding="utf-8"))
    assertions = json.loads((DATA / "assertions-v3.json").read_text(encoding="utf-8"))
    lines = [
        "# 63 个检查点索引", "",
        "所有题目均为虚构的合成评测数据。字段以结构化题库为准，此处展示触发原文、证据与规则数。", "",
        "| 检查点 | 维度 | Session / 轮次 | 触发话术 | 证据 | 规则数 |",
        "|---|---|---|---|---|---:|",
    ]
    for checkpoint in persona["checkpoints"]:
        spec = assertions[checkpoint["id"]]
        trigger = spec["trigger"].replace("|", "\\|").replace("\n", " ")
        evidence = ", ".join(spec.get("evidence", []))
        lines.append(
            f"| {checkpoint['id']} | {checkpoint['dim']} | "
            f"{checkpoint['session']} / {spec['turn']} | {trigger} | "
            f"{evidence} | {len(spec['rules'])} |"
        )
    lines.extend([
        "",
        "完整规则见 [assertions-v3.json](../persona-01-linzhou/data/assertions-v3.json)，"
        "期望行为与指标见 [persona-01.json](../persona-01-linzhou/data/persona-01.json)。",
        "",
        "末尾声明：本索引中的用户、经历和对话均为虚构，不对应真实个人或业务记录。", "",
    ])
    (DOCS / "checkpoint-index.md").write_text("\n".join(lines), encoding="utf-8")


def trace_availability() -> None:
    records = {
        "synthetic_data": True,
        "api_structured_runs": {
            "available": True,
            "location": "persona-01-linzhou/results/",
            "fields_observed": ["context", "reply", "tool_calls", "score", "perf", "retrieval"],
            "coverage": "Varies by file and historical run; missing fields are not inferred",
        },
        "gpt_frozen_inputs": {
            "available": True, "expected_files": 252,
            "location": "persona-01-linzhou/results/gpt-runtime/inputs/",
        },
        "gpt_structured_replies": {
            "available": True, "expected_files": 756,
            "location": "persona-01-linzhou/results/gpt-runtime/replies/",
        },
        "gpt_complete_execution_traces": {
            "available": False,
            "missing": [
                "Complete sub-agent orchestration logs",
                "Verified complete-input read evidence before every reply",
                "Real tool side effects and state transitions",
            ],
            "note": "Structured context and replies are not represented as full execution traces",
        },
        "sampled_trace_analysis": {
            "available": True,
            "location": "persona-01-linzhou/results/glm-v2/",
            "note": "Only the analyses actually saved on disk are included",
        },
    }
    (DOCS / "trace-availability.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    checkpoint_index()
    trace_availability()
    print("Generated checkpoint index and trace availability")


if __name__ == "__main__":
    main()
