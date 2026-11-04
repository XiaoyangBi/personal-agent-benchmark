#!/usr/bin/env python3
"""Validate the completed API suite: coverage, invalid-item accounting, first-valid
retention, offline score recomputation and cross-artifact ranking consistency.

Invalid items are never scored as failures: transport errors, empty replies,
missing structured arrays and checkpoints dropped on task failure are counted
and excluded from the five-model common denominator.
"""

import importlib.util
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODELS = ["deepseek-v4-flash", "minimax-m3.1-flash", "glm-5.3-flash", "hy4-preview", "mimo-v2.6-flash"]
CONDITIONS = ("C0", "C1", "C2", "C3")
TAG = "api-v2-nothink"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


suite = load_module("api_suite_for_validation", ROOT / "tools" / "evaluation" / "run_api_suite.py")
rank = load_module("api_rank_for_validation", ROOT / "tools" / "evaluation" / "rank_api_suite.py")
engine = load_module("api_assertions_for_validation", ROOT / "persona-01-linzhou" / "runner" / "assertions.py")


def reply_digest(run):
    return json.dumps(run.get("reply"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def classify(run):
    """Return a reason string for an invalid run, or None when it is valid."""
    reply = run.get("reply") or {}
    if reply.get("error"):
        return "transport_error"
    if not isinstance(reply.get("text"), str):
        return "bad_text_type"
    if any(not isinstance(reply.get(key), list) for key in ("payload", "citations", "tool_calls")):
        return "missing_structured_fields"
    if not reply["text"].strip() and not reply["tool_calls"]:
        return "empty_response"
    if (run.get("score") or {}).get("passed") is None:
        return "unscorable"
    return None


def main():
    errors = []
    persona_roots = sorted(p for p in ROOT.glob("persona-*") if p.is_dir() and (p / "data").is_dir())
    expected_persona_keys = {(f"CP{i:02d}", c) for i in range(1, 64) for c in CONDITIONS}
    model_reports = []
    model_valid_keys = {}
    model_passed_full = {}

    for model in MODELS:
        valid_total = 0
        recorded_calls = 0
        attempt_files_count = 0
        reasons = Counter()
        absent_keys = 0
        valid_keys_global = set()
        passed_full = set()
        for root in persona_roots:
            pid = root.name
            path = root / "results" / f"{TAG}-{model}.json"
            if not path.exists():
                errors.append(f"missing {path.relative_to(ROOT)}")
                continue
            result = json.loads(path.read_text(encoding="utf-8"))
            meta = result.get("meta", {})
            if meta.get("model") != model or meta.get("persona") != pid or meta.get("scoring_spec") != "assertions.json":
                errors.append(f"{model}/{pid}: metadata mismatch")
            specs = json.loads((root / "data" / "assertions.json").read_text(encoding="utf-8"))
            runs = {}
            for run in result.get("runs", []):
                key = (run["cp"], run["condition"])
                if key in runs:
                    errors.append(f"{model}/{pid}/{key}: duplicate key in final")
                runs[key] = run
            absent = expected_persona_keys - set(runs)
            absent_keys += len(absent)
            valid_keys = set()
            for key, run in runs.items():
                reason = classify(run)
                if reason:
                    reasons[reason] += 1
                    continue
                recomputed = engine.evaluate(run["reply"], specs[key[0]]["rules"])
                if recomputed != run.get("score"):
                    errors.append(f"{model}/{pid}/{key}: score mismatch")
                if recomputed["passed"] is None:
                    errors.append(f"{model}/{pid}/{key}: score is None for a valid run")
                    continue
                valid_keys.add(key)
                valid_keys_global.add((pid, key[0], key[1]))
                if recomputed["passed"]:
                    passed_full.add((pid, key[0], key[1]))
            # Audit first-valid retention against every preserved attempt.
            first_valid = {}
            attempt_dir = root / "results"
            attempts = sorted(attempt_dir.glob(f"{TAG}-{model}-attempt*.json"), key=suite.attempt_number)
            for attempt in attempts:
                attempt_files_count += 1
                value = json.loads(attempt.read_text(encoding="utf-8"))
                recorded_calls += len(value.get("runs", [])) + int(value.get("meta", {}).get("stats", {}).get("retries", 0))
                for run in value.get("runs", []):
                    key = (run["cp"], run["condition"])
                    if key not in first_valid and classify(run) is None:
                        first_valid[key] = run
            for key in valid_keys & set(first_valid):
                if reply_digest(runs[key]) != reply_digest(first_valid[key]):
                    errors.append(f"{model}/{pid}/{key}: final reply is not first valid attempt")
            valid_total += len(valid_keys)
        model_valid_keys[model] = valid_keys_global
        model_passed_full[model] = passed_full
        model_reports.append({
            "model": model, "valid_items": valid_total, "absent_keys": absent_keys,
            "invalid_by_reason": dict(sorted(reasons.items())),
            "recorded_http_attempts": recorded_calls, "attempt_files": attempt_files_count,
        })

    # Cross-check the ranking artifact against an independent recomputation.
    ranking_path = ROOT / "docs" / f"{TAG}-ranking.json"
    common = set.intersection(*model_valid_keys.values())
    if not ranking_path.exists():
        errors.append("ranking JSON missing")
    else:
        ranking = json.loads(ranking_path.read_text(encoding="utf-8"))
        if ranking.get("status") != "complete":
            errors.append("ranking status is not complete")
        if ranking.get("common_items") != len(common):
            errors.append(f"ranking common_items {ranking.get('common_items')} != recomputed {len(common)}")
        if ranking.get("expected_items") != 2520:
            errors.append("ranking expected_items != 2520")
        for row in ranking.get("models", []):
            model = row["model"]
            expected_passed = len(model_passed_full.get(model, set()) & common)
            if row["passed"] != expected_passed or row["total"] != len(common):
                errors.append(f"ranking counts mismatch for {model}: {row['passed']} vs {expected_passed}")
        expected_order = sorted(ranking.get("models", []), key=lambda r: (-r["passed"], r["model"]))
        if [r["model"] for r in ranking.get("models", [])] != [r["model"] for r in expected_order]:
            errors.append("ranking order inconsistent with pass counts")

    # The sensitivity analysis must agree on the rank order.
    sensitivity_path = ROOT / "docs" / f"{TAG}-sensitivity.json"
    if not sensitivity_path.exists():
        errors.append("sensitivity JSON missing")
    else:
        sensitivity = json.loads(sensitivity_path.read_text(encoding="utf-8"))
        if not sensitivity.get("rank_order_consistent"):
            errors.append("sensitivity policies disagree on rank order")
        if sensitivity.get("primary_common_items") != len(common):
            errors.append("sensitivity primary common items differ from recomputation")

    report = {
        "schema": "personal-agent-api-validation-v1",
        "status": "pass" if not errors else "fail",
        "tag": TAG,
        "expected_items": 2520, "common_items": len(common),
        "excluded_items": 2520 - len(common),
        "models": model_reports,
        "recorded_http_note": "Recorded attempts equal saved runs plus runner-recorded transport retries; interrupted in-flight calls and smoke tests are excluded.",
        "first_valid_policy": "A later attempt can only fill a missing or technically invalid key; valid replies are never replaced by score.",
        "invalid_item_policy": "Transport errors, empty replies, missing structured arrays and checkpoints dropped by task failure are classified, excluded from the common denominator, and never scored as failures.",
        "errors": errors,
    }
    (ROOT / "docs" / f"{TAG}-validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "common_items": len(common),
                      "excluded_items": 2520 - len(common),
                      "errors": errors[:20], "models": model_reports}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
