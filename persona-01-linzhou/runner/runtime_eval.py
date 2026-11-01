#!/usr/bin/env python3
"""Export blinded single-item runtime inputs and collect unchanged model replies.

Runtime results are deliberately separate from API-model leaderboards. Each
item must be answered in a new explicitly selected model session. This adapter
never invokes the model or repairs an answer and never exposes scoring rules
in the exported inputs.
"""

import argparse
import hashlib
import json
import statistics
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

import assertions
import conditions
import runner
from memory import NaiveMemory

MODEL = "gpt-6.1-sol"
BUDGET = 8000
ROOT = runner.ROOT
DEST = ROOT / "results" / "gpt-runtime"
MANIFEST = DEST / "manifest.json"
REQUIRED_FIELDS = {"text": str, "payload": list, "citations": list, "tool_calls": list}
EXTERNAL_FILES = {
    "glm": ["glm-v2/all-v2.json", "rep2-glm.json"],
    "hy4": ["hy4-v2/results-v2-full-hy4b.json", "hy4-v2/results-v2-hy4-rep2.json", "hy4-v2/results-v2-hy4-rep3.json"],
    "mimo": ["rep1-mimo.json", "rep2-mimo.json", "rep3-mimo.json"],
    "minimax": ["minimax-v2/all-v2.json", "rep2-minimax.json", "rep3-minimax-full.json", "rep4-minimax.json"],
    "deepseek": ["all-v2.json", "rep2-deepseek.json", "rep3-deepseek.json", "rep4-deepseek.json"],
}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    if not path.parent.is_dir():
        raise ValueError(f"Output parent is missing: {path.parent}")
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def digest(value):
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prepare():
    if MANIFEST.exists():
        raise ValueError("Manifest already exists; refusing to replace an active evaluation")
    if not runner.RESULTS.is_dir():
        raise ValueError("Project results directory does not exist")
    for folder in (DEST, DEST / "inputs", DEST / "replies", DEST / "replies" / "r1"):
        folder.mkdir(exist_ok=True)
    persona = runner.load_json("persona-01.json")
    source = runner.load_json("assertions.json")
    sessions = conditions.load_sessions()
    memory = NaiveMemory()
    for sid in sorted(sessions, key=conditions.sid_index):
        memory.insert(sid, "\n".join(sessions[sid]["turns"]), conditions.sid_index(sid))
    samples = []
    for cp in persona["checkpoints"]:
        spec = source.get(cp["id"])
        if spec is None:
            continue
        for cond in runner.CONDITIONS:
            context = conditions.build(
                {**cp, "evidence": spec.get("evidence", [])}, cond,
                sessions, memory, BUDGET, spec["trigger"], spec.get("turn"),
            )
            messages = conditions.build_messages(runner.SYSTEM, context, spec["trigger"], runner.REPLY_HINT, spec.get("env", ""))
            item = f"{len(samples) + 1:03d}"
            value = {"messages": messages}
            write_json(DEST / "inputs" / f"{item}.json", value)
            samples.append({"item": item, "cp": cp["id"], "condition": cond, "session": cp["session"], "dim": cp["dim"], "context": {key: context[key] for key in ("ids", "tokens", "policy", "truncated", "dropped", "turn")}, "input_sha256": digest(value)})
    if len(samples) != 252:
        raise ValueError(f"Expected 252 items, got {len(samples)}")
    manifest = {
        "meta": {"model": MODEL, "mode": "workbuddy_runtime", "prepared_at": datetime.now(timezone.utc).isoformat(), "budget": BUDGET, "persona": persona["persona_id"], "conditions": runner.CONDITIONS, "scoring_spec": "assertions-v3.json", "input_spec": "assertions.json", "input_spec_sha256": digest(source), "transport": "fresh Agent session; explicit model selection; one input-file read; one reply-file write", "temperature": None, "temperature_control": "not exposed", "native_actions": "disabled for simulated scenario; only read input and write reply", "ranking_scope": "separate runtime track; descriptive API references only"},
        "samples": samples,
    }
    write_json(MANIFEST, manifest)
    print(f"Prepared {len(samples)} blinded items in {DEST}")


def validate_reply(reply):
    if not isinstance(reply, dict):
        raise ValueError("Reply must be a JSON object")
    for field, kind in REQUIRED_FIELDS.items():
        if not isinstance(reply.get(field), kind):
            raise ValueError(f"Invalid or missing field: {field}")
    for call in reply["tool_calls"]:
        if not isinstance(call, dict) or not isinstance(call.get("tool"), str) or not isinstance(call.get("params"), dict):
            raise ValueError("Invalid simulated tool call schema")
    if reply.get("error"):
        raise ValueError("Reply contains an error field")


def score_map(runs, spec):
    return {(run["cp"], run["condition"]): bool(assertions.evaluate(run["reply"], spec[run["cp"]]["rules"])["passed"]) for run in runs if not run.get("reply", {}).get("error")}


def collect(round_name):
    manifest = read_json(MANIFEST)
    spec = runner.load_json("assertions-v3.json")
    runs, missing, invalid = [], [], []
    for sample in manifest["samples"]:
        item = sample["item"]
        if digest(read_json(DEST / "inputs" / f"{item}.json")) != sample["input_sha256"]:
            raise ValueError(f"Input changed after preparation: {item}")
        path = DEST / "replies" / round_name / f"{item}.json"
        if not path.exists():
            missing.append(item)
            continue
        try:
            reply = read_json(path)
            validate_reply(reply)
        except (ValueError, OSError) as exc:
            invalid.append({"item": item, "error": str(exc)})
            continue
        runs.append({key: sample[key] for key in ("cp", "condition", "session", "dim", "context")} | {"reply": reply, "score": assertions.evaluate(reply, spec[sample["cp"]]["rules"]), "perf": {"latency_ms": None, "tokens_in": None, "tokens_out": None}, "gate": None, "provenance": {"item": item, "input_sha256": sample["input_sha256"], "reply_sha256": digest(reply)}})
    output = {"meta": manifest["meta"] | {"run_id": f"{round_name}-gpt-runtime", "collected_at": datetime.now(timezone.utc).isoformat(), "complete": not missing and not invalid, "coverage": {"completed": len(runs), "expected": len(manifest["samples"])}, "missing": missing, "invalid": invalid, "scoring_sha256": digest(spec)}, "runs": runs}
    write_json(DEST / f"{round_name}.json", output)
    print(json.dumps({"completed": len(runs), "expected": len(manifest["samples"]), "missing": missing, "invalid": invalid, "passed": sum(r["score"]["passed"] for r in runs)}, ensure_ascii=False))
    if missing or invalid:
        return
    runtime = score_map(runs, spec)
    externals = {name: [score_map(read_json(runner.RESULTS / f)["runs"], spec) for f in files] for name, files in EXTERNAL_FILES.items()}
    common = set(runtime)
    for rounds in externals.values():
        for row in rounds:
            common &= set(row)
    def stats(rows, keys):
        rates = [sum(row[k] for k in keys) / len(keys) for row in rows]
        return {"rounds": len(rows), "rate": statistics.fmean(rates), "sd": statistics.stdev(rates) if len(rates) > 1 else None, "per_condition": {cond: statistics.fmean(sum(row[k] for k in keys if k[1] == cond) / sum(k[1] == cond for k in keys) for row in rows) for cond in runner.CONDITIONS}}
    comparison = {"scope": "Descriptive only. Runtime and API environments differ; no pooled ranking or pairwise significance.", "common_items": len(common), "common_per_condition": {cond: sum(k[1] == cond for k in common) for cond in runner.CONDITIONS}, "runtime_full": stats([runtime], set(runtime)), "runtime_common": stats([runtime], common), "api_reference": {name: stats(rows, common) for name, rows in externals.items()}, "failures": [{"cp": run["cp"], "condition": run["condition"], "details": [d for d in run["score"]["details"] if not d["ok"]]} for run in runs if not run["score"]["passed"]]}
    write_json(DEST / f"{round_name}-analysis.json", comparison)
    print(json.dumps({k: v for k, v in comparison.items() if k != "failures"}, ensure_ascii=False, indent=2))


def stability_metrics(rows, keys):
    """Describe round-level and item-level variability on identical keys."""
    if len(rows) < 2 or not keys:
        raise ValueError("Stability requires multiple rounds and nonempty common keys")
    if any(not keys.issubset(row) for row in rows):
        raise ValueError("Every round must contain all selected keys")
    counts = [sum(row[key] for key in keys) for row in rows]
    rates = [count / len(keys) for count in counts]
    pairs = []
    for left, right in combinations(range(len(rows)), 2):
        changed = sum(rows[left][key] != rows[right][key] for key in keys)
        pairs.append({"rounds": [left + 1, right + 1], "changed": changed, "rate": changed / len(keys)})
    histogram = {
        str(count): sum(sum(row[key] for row in rows) == count for key in keys)
        for count in range(len(rows) + 1)
    }
    unanimous_pass = histogram[str(len(rows))]
    unanimous_fail = histogram["0"]
    mixed = len(keys) - unanimous_pass - unanimous_fail
    return {
        "items": len(keys), "rounds": len(rows), "passed_per_round": counts,
        "rates_per_round": rates, "mean_rate": statistics.fmean(rates),
        "sample_sd": statistics.stdev(rates), "range": max(rates) - min(rates),
        "pairwise_flips": pairs, "mean_pairwise_flip_rate": statistics.fmean(pair["rate"] for pair in pairs),
        "mixed_count": mixed, "mixed_rate": mixed / len(keys),
        "always_pass_count": unanimous_pass, "always_fail_count": unanimous_fail,
        "all_agree_rate": (unanimous_pass + unanimous_fail) / len(keys),
        "pass_count_histogram": histogram,
    }


def stability():
    """Re-score three models x three rounds without modifying source replies."""
    round_names = ("r1", "r2", "r3")
    sources = {
        "gpt-runtime": [DEST / f"{name}.json" for name in round_names],
        "hy4": [runner.RESULTS / name for name in EXTERNAL_FILES["hy4"]],
        "mimo": [runner.RESULTS / name for name in EXTERNAL_FILES["mimo"]],
    }
    spec = runner.load_json("assertions-v3.json")
    manifest = read_json(MANIFEST)
    inputs_changed = any(
        digest(read_json(DEST / "inputs" / f"{sample['item']}.json")) != sample["input_sha256"]
        for sample in manifest["samples"]
    )
    if inputs_changed:
        raise ValueError("Frozen input changed")
    maps, provenance, excluded = {}, {}, []
    for model, paths in sources.items():
        model_rows, files = [], []
        for round_index, path in enumerate(paths, start=1):
            value = read_json(path)
            if model == "gpt-runtime" and not value["meta"].get("complete"):
                raise ValueError(f"Incomplete GPT round: {path.name}")
            row = score_map(value["runs"], spec)
            eligible = sum(not run.get("reply", {}).get("error") for run in value["runs"])
            if len(row) != eligible:
                raise ValueError(f"Duplicate sample keys: {path}")
            model_rows.append(row)
            files.append({"path": str(path.relative_to(ROOT)), "sha256": digest(value), "valid_items": len(row)})
            excluded.extend(
                {
                    "model": model, "round": round_index, "cp": run["cp"],
                    "condition": run["condition"], "reason": str(run["reply"]["error"]),
                }
                for run in value["runs"] if run.get("reply", {}).get("error")
            )
        maps[model], provenance[model] = model_rows, files
    common = set.intersection(*(set(row) for rows in maps.values() for row in rows))
    if not common:
        raise ValueError("No common valid samples across nine rounds")
    per_condition = {condition: {key for key in common if key[1] == condition} for condition in runner.CONDITIONS}
    results = {model: stability_metrics(rows, common) | {
        "conditions": {condition: stability_metrics(rows, keys) for condition, keys in per_condition.items() if keys}
    } for model, rows in maps.items()}
    matrix = [
        {
            "cp": key[0], "condition": key[1],
            **{model: [row[key] for row in rows] for model, rows in maps.items()},
        }
        for key in sorted(common)
    ]
    gpt_keys = set.intersection(*(set(row) for row in maps["gpt-runtime"]))
    output = {
        "meta": {
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "scoring_spec": "assertions-v3.json", "scoring_sha256": digest(spec),
            "rounds_per_model": len(round_names), "common_items": len(common),
            "common_per_condition": {condition: len(keys) for condition, keys in per_condition.items()},
            "scope": (
                "Descriptive only. GPT uses WorkBuddy runtime; Hy4 and MiMo use API. "
                "No cross-track significance or causal ranking."
            ),
            "definitions": {
                "sample_sd": "Sample SD of round pass rates, ddof=1; not a standard error",
                "mean_pairwise_flip_rate": "Mean disagreement fraction across all three round pairs",
                "mixed_rate": "Fraction of items not unanimously pass/fail across the three rounds",
            },
            "limitations": [
                "Three rounds only", "Checkpoints and conditions are not independent personas",
                "Fixed assertions have known false positives/negatives",
                "Runtime wrapper and technical retries differ from API sampling",
                "Not a completed execution-trace read audit", "No latency, cost or CFI comparisons",
            ],
        },
        "sources": provenance, "excluded_error_runs": excluded, "models": results,
        "gpt_full": stability_metrics(maps["gpt-runtime"], gpt_keys),
        "matrix": matrix,
    }
    write_json(DEST / "stability-three-models.json", output)
    summary = {key: output[key] for key in ("meta", "models", "gpt_full", "excluded_error_runs")}
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "collect", "stability"))
    parser.add_argument("--round", default="r1", choices=("r1", "r2", "r3"))
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    elif args.action == "stability":
        stability()
    else:
        collect(args.round)


if __name__ == "__main__":
    main()
