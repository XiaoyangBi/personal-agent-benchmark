#!/usr/bin/env python3
"""Build model-oriented navigation from the immutable run inventory."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "persona-01-linzhou" / "results"
INVENTORY = ROOT / "docs" / "run-inventory.json"

MODELS = {
    "deepseek-v4-flash": {
        "name": "DeepSeek",
        "primary": "results/all-v2.json",
        "note": "主结果文件名不含模型名；按 meta.model 识别。",
    },
    "minimax-m3.1-flash": {
        "name": "MiniMax",
        "primary": "results/minimax-v2/all-v2.json",
        "note": "另保留 rep 前缀的重复实验和重试记录。",
    },
    "glm-5.3-flash": {
        "name": "GLM",
        "primary": "results/glm-v2/all-v2.json",
        "note": "包含分段、重试、条件级合并及已保存的抽样 trace 分析。",
    },
    "hy4-preview": {
        "name": "混元 Hy4",
        "primary": "results/hy4-v2/results-v2-full-hy4b.json",
        "note": "三轮稳定性使用 hy4-v2 下首轮及 rep2、rep3 的共同有效样本。",
    },
    "mimo-v2.6-flash": {
        "name": "MiMo",
        "primary": "results/rep1-mimo.json",
        "note": "三轮结果使用根 results 下的 rep1-mimo、rep2-mimo、rep3-mimo。",
    },
    "gpt-6.1-sol": {
        "name": "GPT 运行时",
        "primary": "results/gpt-runtime/r1.json",
        "note": "独立运行时轨道；冻结输入、逐条回复及三轮汇总另见 gpt-runtime。",
    },
}


def main() -> None:
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    output = []
    for model_id, config in MODELS.items():
        rows = [r for r in inventory if model_id in r.get("models", [])]
        primary = next((r for r in rows if r["path"] == config["primary"]), None)
        if primary is None:
            raise ValueError(f"Primary result missing for {model_id}: {config['primary']}")
        if not (RESULTS.parent / primary["path"]).is_file():
            raise FileNotFoundError(primary["path"])
        output.append({
            "model": model_id,
            "display_name": config["name"],
            "result_files": len(rows),
            "run_records": sum(int(r.get("runs") or 0) for r in rows),
            "primary_result": primary,
            "note": config["note"],
            "files": [
                {k: r.get(k) for k in ("path", "runs", "sha256")}
                for r in sorted(rows, key=lambda item: item["path"])
            ],
        })

    payload = {
        "schema": "personal-agent-benchmark-model-results-v1",
        "scope": "Historical persona-01 experiments only. This index does not cover the api-v2-nothink formal round.",
        "persona": "persona-01-linzhou",
        "inventory": "docs/run-inventory.json",
        "counting_note": "run_records includes retries, merged runs and historical experiments; it is not a count of independent model calls.",
        "formal_round": {
            "tag": "api-v2-nothink",
            "description": "Single-round formal evaluation of five API models across ten synthetic personas",
            "ranking": "docs/api-v2-nothink-ranking.md",
            "ranking_json": "docs/api-v2-nothink-ranking.json",
            "validation": "docs/api-v2-nothink-validation.json",
            "sensitivity": "docs/api-v2-nothink-sensitivity.json",
            "result_pattern": "persona-*/results/api-v2-nothink-<model>.json",
        },
        "models": output,
    }
    (ROOT / "docs" / "model-results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "# 按模型查看结果",
        "",
        "## 本轮正式统一评测（五模型 × 十人物单轮）",
        "",
        "正式轨道 `api-v2-nothink`：五家 API 模型在 10 个人物上各跑一轮，结果位于各人物 `results/api-v2-nothink-<模型>.json`。统一排名见 [排名报告](api-v2-nothink-ranking.md)、[机器可读结果](api-v2-nothink-ranking.json)、[口径校验](api-v2-nothink-validation.json) 与 [敏感性分析](api-v2-nothink-sensitivity.json)。这一轨道与下方历史 persona-01 实验分母、量尺、题集均不同，不可混排。",
        "",
        "## 历史 persona-01 实验索引",
        "",
        "下表由 `docs/run-inventory.json` 的结果元数据生成，解决通用文件名和历史目录造成的查找困难。这些文件均属于 persona-01 的早期实验与三轮稳定性素材。",
        "",
        "文件中的 run 记录包含重试、合并和历史实验，不能解释为独立模型调用次数。不同题集、评分版本和运行轨道不可直接混排。",
        "",
        "| 模型 | 主结果入口 | 主结果记录 | 结果文件 | 全部 run 记录 |",
        "|---|---|---:|---:|---:|",
    ]
    for item in output:
        primary = item["primary_result"]
        path = f"../persona-01-linzhou/{primary['path']}"
        lines.append(
            f"| {item['display_name']} (`{item['model']}`) | [{primary['path']}]({path}) "
            f"| {primary['runs']} | {item['result_files']} | {item['run_records']} |"
        )
    lines += ["", "## 查找说明", ""]
    for item in output:
        lines.append(f"- {item['display_name']}：{item['note']}")
    lines += [
        "",
        "每个结果文件的运行数与源 SHA-256 见机器可读索引 [model-results.json](model-results.json)；全部结果（包括无模型元数据的冻结输入和分析文件）仍以 [run-inventory.json](run-inventory.json) 为准。",
        "",
    ]
    (ROOT / "docs" / "model-results.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Indexed {len(output)} models and {sum(x['result_files'] for x in output)} result files")


if __name__ == "__main__":
    main()
