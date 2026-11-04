#!/usr/bin/env python3
"""Recompute and rank the five-model, ten-persona API evaluation."""

import argparse
import hashlib
import importlib.util
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "persona-01-linzhou" / "runner"
MODELS = ["deepseek-v4-flash", "minimax-m3.1-flash", "glm-5.3-flash", "hy4-preview", "mimo-v2.6-flash"]
DISPLAY = {
    "deepseek-v4-flash": "DeepSeek", "minimax-m3.1-flash": "MiniMax",
    "glm-5.3-flash": "GLM", "hy4-preview": "Hy4", "mimo-v2.6-flash": "MiMo",
}
CONDITIONS = ("C0", "C1", "C2", "C3")
TAG = "api-v2-nothink"
DIMS = tuple(f"D{i}" for i in range(1, 8))


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


engine = load_module("rank_assertions", RUNNER / "assertions.py")


def valid_run(run):
    reply = run.get("reply") or {}
    if reply.get("error") or not isinstance(reply.get("text"), str):
        return False
    if any(not isinstance(reply.get(key), list) for key in ("payload", "citations", "tool_calls")):
        return False
    if not reply["text"].strip() and not reply["tool_calls"]:
        return False
    return True


def percentile(sorted_values, fraction):
    if not sorted_values:
        return None
    position = (len(sorted_values) - 1) * fraction
    low = int(position)
    high = min(low + 1, len(sorted_values) - 1)
    weight = position - low
    return sorted_values[low] * (1 - weight) + sorted_values[high] * weight


def collect():
    persona_roots = sorted(p for p in ROOT.glob("persona-*") if p.is_dir() and (p / "data").is_dir())
    if len(persona_roots) != 10:
        raise ValueError(f"Expected ten personas, found {len(persona_roots)}")
    expected = set()
    persona_specs = {}
    cp_dims = {}
    spec_hashes = {}
    for root in persona_roots:
        pid = root.name
        spec_path = root / "data" / "assertions.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        persona_specs[pid] = spec
        spec_hashes[pid] = hashlib.sha256(spec_path.read_bytes()).hexdigest()
        data_file = next((root / "data").glob("persona-*.json"))
        data = json.loads(data_file.read_text(encoding="utf-8"))
        for cp in data["checkpoints"]:
            cp_dims[(pid, cp["id"])] = cp["dim"]
            expected.update((pid, cp["id"], condition) for condition in CONDITIONS)

    stats = {}
    sources = []
    for model in MODELS:
        model_stats = {
            "valid": set(), "passed": set(), "persona": defaultdict(lambda: [0, 0]),
            "condition": defaultdict(lambda: [0, 0]), "dimension": defaultdict(lambda: [0, 0]),
            "tokens_in": 0, "tokens_out": 0, "latencies": [], "invalid": 0, "decode_modes": set(),
        }
        for root in persona_roots:
            pid = root.name
            path = root / "results" / f"{TAG}-{model}.json"
            if not path.exists():
                sources.append({"model": model, "persona": pid, "path": str(path.relative_to(ROOT)), "missing": True})
                continue
            result = json.loads(path.read_text(encoding="utf-8"))
            meta = result.get("meta", {})
            if meta.get("model") != model or meta.get("persona") != pid or meta.get("scoring_spec") != "assertions.json":
                raise ValueError(f"Metadata mismatch: {path}")
            model_stats["decode_modes"].add(bool(meta.get("no_thinking")))
            seen = set()
            for run in result.get("runs", []):
                key = (pid, run["cp"], run["condition"])
                if key in seen:
                    raise ValueError(f"Duplicate key {key} in {path}")
                seen.add(key)
                if not valid_run(run):
                    model_stats["invalid"] += 1
                    continue
                score = engine.evaluate(run["reply"], persona_specs[pid][run["cp"]]["rules"])
                if score["passed"] is None:
                    model_stats["invalid"] += 1
                    continue
                model_stats["valid"].add(key)
                passed = bool(score["passed"])
                if passed:
                    model_stats["passed"].add(key)
                for group, group_key in (
                    (model_stats["persona"], pid),
                    (model_stats["condition"], run["condition"]),
                    (model_stats["dimension"], cp_dims[key[:2]]),
                ):
                    group[group_key][0] += int(passed)
                    group[group_key][1] += 1
                perf = run.get("perf") or {}
                model_stats["tokens_in"] += int(perf.get("tokens_in") or 0)
                model_stats["tokens_out"] += int(perf.get("tokens_out") or 0)
                if perf.get("latency_ms") is not None:
                    model_stats["latencies"].append(int(perf["latency_ms"]))
            sources.append({
                "model": model, "persona": pid, "path": str(path.relative_to(ROOT)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "runs": len(result.get("runs", [])),
                "no_thinking": meta.get("no_thinking"), "meta_complete": bool(meta.get("complete")),
            })
        stats[model] = model_stats
    return expected, stats, sources, spec_hashes


def summarize(expected, stats, sources, spec_hashes, require_complete):
    common = set.intersection(*(stats[model]["valid"] for model in MODELS)) if stats else set()
    coverage = {model: {"valid": len(stats[model]["valid"]), "expected": len(expected),
                        "passed": len(stats[model]["passed"])} for model in MODELS}
    if require_complete and (len(common) != len(expected) or any(len(stats[m]["valid"]) != len(expected) for m in MODELS)):
        return {"status": "incomplete", "expected_items": len(expected), "common_items": len(common),
                "coverage": coverage, "sources": sources}

    rows = []
    for model in MODELS:
        item = stats[model]
        passed = len(item["passed"] & common)
        total = len(common)
        persona_rates = {pid: values[0] / values[1] for pid, values in item["persona"].items() if values[1]}
        ordered_rates = sorted(persona_rates.values())
        rng = random.Random(20261102 + MODELS.index(model))
        boot = sorted(sum(rng.choice(ordered_rates) for _ in ordered_rates) / len(ordered_rates) for _ in range(5000))
        latencies = sorted(item["latencies"])
        rows.append({
            "model": model, "display_name": DISPLAY[model], "passed": passed, "total": total,
            "no_thinking": sorted(item["decode_modes"]),
            "pass_rate": passed / total if total else None,
            "persona_rates": persona_rates,
            "persona_sd": statistics.stdev(ordered_rates) if len(ordered_rates) > 1 else 0,
            "persona_min": min(ordered_rates) if ordered_rates else None,
            "persona_max": max(ordered_rates) if ordered_rates else None,
            "persona_bootstrap_95": [percentile(boot, 0.025), percentile(boot, 0.975)],
            "condition": {key: {"passed": v[0], "total": v[1], "rate": v[0] / v[1]} for key, v in item["condition"].items()},
            "dimension": {key: {"passed": v[0], "total": v[1], "rate": v[0] / v[1]} for key, v in item["dimension"].items()},
            "tokens_in": item["tokens_in"], "tokens_out": item["tokens_out"],
            "latency_ms": {"mean": statistics.mean(latencies) if latencies else None,
                           "p50": percentile(latencies, 0.5), "p95": percentile(latencies, 0.95)},
        })
    rows.sort(key=lambda row: (-row["passed"], row["model"]))
    for index, row in enumerate(rows):
        row["rank"] = 1 + sum(other["passed"] > row["passed"] for other in rows)

    # Leave-one-persona-out ranks: sensitivity to any single synthetic person.
    for row in rows:
        model = row["model"]
        lopo = []
        for excluded in row["persona_rates"]:
            scores = {}
            for other in rows:
                other_model = other["model"]
                kept = [rate for pid, rate in other["persona_rates"].items() if pid != excluded]
                scores[other_model] = sum(kept) / len(kept)
            target = scores[model]
            lopo.append(1 + sum(score > target for key, score in scores.items() if key != model))
        row["lopo_rank_min"] = min(lopo)
        row["lopo_rank_max"] = max(lopo)

    pairwise = []
    for left in MODELS:
        for right in MODELS:
            if left >= right:
                continue
            left_pass = stats[left]["passed"] & common
            right_pass = stats[right]["passed"] & common
            pairwise.append({
                "a": left, "b": right,
                "a_only": len(left_pass - right_pass), "b_only": len(right_pass - left_pass),
                "both_pass": len(left_pass & right_pass),
                "both_fail": len(common) - len(left_pass | right_pass),
            })
    return {
        "schema": "personal-agent-api-ranking-v1", "status": "complete", "tag": TAG,
        "scope": "Five API models, ten synthetic personas, 63 checkpoints, C0-C3, one round, validated model-specific decoding, assertions.json",
        "expected_items": len(expected), "common_items": len(common), "coverage": coverage,
        "excluded_items": sorted(expected - common),
        "ranking_metric": "Pooled pass rate over the common valid items; equal item counts per persona also make this the persona macro average.",
        "uncertainty": "Persona SD, min/max, deterministic persona-cluster bootstrap 95% interval and leave-one-persona-out rank range. Not a repeated-sample significance test.",
        "models": rows, "pairwise": pairwise, "sources": sources, "scoring_sha256": spec_hashes,
        "limitations": [
            "One API round per model; no stochastic repeat variance or significance claim.",
            "DeepSeek, GLM, Hy4 and MiMo use non-thinking output. MiniMax uses standard output because the gateway returns an unparsable payload when thinking is disabled. Decoding mode is per-model validated but remains a confound.",
            "Fixed lexical, structural and tool assertions are weak proxies for semantic quality.",
            "Synthetic personas share scenario archetypes and are not independent real-user samples.",
            "C3 uses the naive bigram retriever, not a production memory system.",
            "GPT runtime results are a separate track and are excluded from this API ranking.",
            "Items with no valid reply from any model are excluded from the common denominator rather than scored as failures.",
            "Token usage and latency are descriptive; no price table or cost ranking is inferred.",
        ],
    }


def write_markdown(report, path):
    excluded = len(report["excluded_items"])
    lines = [
        "# 五模型 × 十人物 API 单轮排名", "",
        "统一使用各人物 `assertions.json` 离线复算，只统计五家共同有效样本。DeepSeek、GLM、Hy4、MiMo 使用非推理输出；MiniMax 使用标准输出，因为网关在关闭思考时返回不可解析的结构。解码模式按模型验证但仍是混杂因素，结果是配置受控的任务表现对比，不是纯推理能力实验。主榜不包含 GPT 运行时，也不把 fixture 或技术错误按 0 分充数。", "",
        f"共同样本：{report['common_items']} / {report['expected_items']}，排除 {excluded} 个无共同有效回复的条目。每模型目标 2520 条，每人物 252 条，单轮。", "",
        "无效项口径：传输错误、空响应、缺结构化字段、整题未写入一律不计 0 分，也不计入分母；只从五家共同有效样本中剔除。分项数量见 `docs/api-v2-nothink-validation.json`。", "",
        "| 排名 | 模型 | 通过数 | 通过率 | 人物间SD | 人物聚类bootstrap 95%区间 | 逐剔人物名次范围 |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    for row in report["models"]:
        interval = row["persona_bootstrap_95"]
        lines.append(f"| {row['rank']} | {row['display_name']} (`{row['model']}`) | {row['passed']}/{row['total']} | {row['pass_rate']:.2%} | {row['persona_sd']:.2%} | {interval[0]:.2%}–{interval[1]:.2%} | {row['lopo_rank_min']}–{row['lopo_rank_max']} |")
    lines += ["", "## 分条件通过率", "", "| 模型 | C0 | C1 | C2 | C3 |", "|---|---:|---:|---:|---:|"]
    for row in report["models"]:
        lines.append(f"| {row['display_name']} | " + " | ".join(f"{row['condition'][c]['rate']:.2%}" for c in CONDITIONS) + " |")
    lines += ["", "## 分维度通过率", "", "| 维度 | " + " | ".join(row["display_name"] for row in report["models"]) + " |", "|---|" + "---:|" * len(report["models"])]
    for dim in DIMS:
        lines.append(f"| {dim} | " + " | ".join(f"{row['dimension'][dim]['rate']:.2%}" for row in report["models"]) + " |")
    lines += ["", "## 分人物通过率", "", "| 人物 | " + " | ".join(row["display_name"] for row in report["models"]) + " |", "|---|" + "---:|" * len(report["models"])]
    persona_ids = sorted(report["models"][0]["persona_rates"])
    for pid in persona_ids:
        lines.append(f"| {pid} | " + " | ".join(f"{row['persona_rates'][pid]:.2%}" for row in report["models"]) + " |")
    lines += ["", "## 逐题判定差异", "", "`a_only` / `b_only` 是共同样本中仅一方通过的条目数；两者不等同于统计显著差异。", "", "| 模型A | 模型B | 仅A通过 | 仅B通过 | 同过 | 同败 |", "|---|---|---:|---:|---:|---:|"]
    for pair in report["pairwise"]:
        lines.append(f"| {DISPLAY[pair['a']]} | {DISPLAY[pair['b']]} | {pair['a_only']} | {pair['b_only']} | {pair['both_pass']} | {pair['both_fail']} |")
    lines += ["", "## 口径与限制", ""]
    lines += [f"- {item}" for item in report["limitations"]]
    lines += ["", "人物聚类区间由固定随机种子的5000次人物重采样得到；逐剔人物名次范围每次移除一个人物后重算总分与排名。它们用于观察合成人物敏感性，不是模型重复采样置信区间。", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", action="store_true", help="Only print coverage; never write ranking files")
    parser.add_argument("--allow-partial", action="store_true", help="Rank only the current common subset, explicitly marked by item counts")
    args = parser.parse_args()
    expected, stats, sources, hashes = collect()
    report = summarize(expected, stats, sources, hashes, require_complete=not args.allow_partial)
    if args.status:
        print(json.dumps({key: report[key] for key in ("status", "expected_items", "common_items", "coverage")}, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "complete" else 1
    if report["status"] != "complete":
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    (ROOT / "docs" / f"{TAG}-ranking.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, ROOT / "docs" / f"{TAG}-ranking.md")
    print(json.dumps({"status": report["status"], "common_items": report["common_items"],
                      "ranking": [{"rank": r["rank"], "model": r["model"], "passed": r["passed"], "rate": r["pass_rate"]} for r in report["models"]]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
