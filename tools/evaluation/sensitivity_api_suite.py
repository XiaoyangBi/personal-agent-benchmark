#!/usr/bin/env python3
"""Check whether the API ranking order survives alternative invalid-item policies.

Four policies are recomputed from the saved result files; no model calls are made.
A: primary ranking, five-model common valid items only (invalid items excluded).
B: full 2520-item denominator, every invalid or missing item counted as a failure.
C: each model's own valid items as its own denominator (coverage differs by model).
D: like A, but replies with text and no structured arrays are normalized to empty
   arrays and scored, mirroring the runner's post-fix normalization.
The report is written to docs/api-v2-nothink-sensitivity.json.
"""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODELS = ["deepseek-v4-flash", "minimax-m3.1-flash", "glm-5.3-flash", "hy4-preview", "mimo-v2.6-flash"]
CONDITIONS = ("C0", "C1", "C2", "C3")
TAG = "api-v2-nothink"
DISPLAY = {
    "deepseek-v4-flash": "DeepSeek", "minimax-m3.1-flash": "MiniMax",
    "glm-5.3-flash": "GLM", "hy4-preview": "Hy4", "mimo-v2.6-flash": "MiMo",
}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


engine = load_module("sensitivity_assertions", ROOT / "persona-01-linzhou" / "runner" / "assertions.py")
rank_lib = load_module("sensitivity_rank", ROOT / "tools" / "evaluation" / "rank_api_suite.py")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def collect_replies():
    """Return {model: {key: (valid, passed, normalized_passed_or_None)}} and the key universe."""
    persona_roots = sorted(p for p in ROOT.glob("persona-*") if p.is_dir() and (p / "data").is_dir())
    data = {m: {} for m in MODELS}
    allkeys = set()
    for root in persona_roots:
        pid = root.name
        assertions = read(root / "data" / "assertions.json")
        allkeys.update((pid, f"CP{i:02d}", c) for i in range(1, 64) for c in CONDITIONS)
        for model in MODELS:
            path = root / "results" / f"{TAG}-{model}.json"
            result = read(path)
            for run in result["runs"]:
                key = (pid, run["cp"], run["condition"])
                reply = run.get("reply") or {}
                norm = None
                if rank_lib.valid_run(run):
                    score = engine.evaluate(reply, assertions[run["cp"]]["rules"])
                    data[model][key] = ("valid", bool(score["passed"]), None)
                else:
                    # Only replies with real text but missing structured arrays are recoverable.
                    if (not reply.get("error") and isinstance(reply.get("text"), str)
                            and reply["text"].strip()):
                        normalized = {"text": reply["text"], "payload": [],
                                      "citations": [], "tool_calls": []}
                        score = engine.evaluate(normalized, assertions[run["cp"]]["rules"])
                        norm = bool(score["passed"])
                    data[model][key] = ("invalid", False, norm)
    return data, allkeys


def ranking(score_map):
    order = sorted(MODELS, key=lambda m: (-score_map[m], m))
    return [{"rank": i + 1, "model": m, "display_name": DISPLAY[m],
             "passed": score_map[m]} for i, m in enumerate(order)]


def main():
    data, allkeys = collect_replies()
    valid_sets = {m: {k for k, v in data[m].items() if v[0] == "valid"} for m in MODELS}

    # Policy A: common valid denominator.
    common_a = set.intersection(*valid_sets.values())
    score_a = {m: sum(1 for k in common_a if data[m][k][1]) for m in MODELS}

    # Policy B: full denominator, invalid/missing = failure.
    score_b = {m: sum(1 for k in allkeys if data[m].get(k, ("invalid", False, None))[1]) for m in MODELS}

    # Policy C: each model's own valid denominator.
    rate_c = {m: (sum(1 for k, v in data[m].items() if v[1]) / len(valid_sets[m])) for m in MODELS}
    order_c = sorted(MODELS, key=lambda m: (-rate_c[m], m))
    ranking_c = [{"rank": i + 1, "model": m, "display_name": DISPLAY[m],
                  "pass_rate": rate_c[m], "denominator": len(valid_sets[m])}
                 for i, m in enumerate(order_c)]

    # Policy D: common denominator after normalizing recoverable replies.
    normalized_data = {m: dict(v) for m, v in data.items()}
    recovered = []
    for m in MODELS:
        for key, value in data[m].items():
            if value[0] == "invalid" and value[2] is not None:
                normalized_data[m][key] = ("valid", value[2], None)
                recovered.append({"model": m, "persona": key[0], "cp": key[1],
                                  "condition": key[2], "passed": value[2]})
    valid_d = {m: {k for k, v in normalized_data[m].items() if v[0] == "valid"} for m in MODELS}
    common_d = set.intersection(*valid_d.values())
    score_d = {m: sum(1 for k in common_d if normalized_data[m][k][1]) for m in MODELS}

    policies = {
        "A_common_valid": {"denominator": len(common_a), "scores": score_a, "ranking": ranking(score_a)},
        "B_full_denominator_invalid_as_zero": {"denominator": len(allkeys), "scores": score_b, "ranking": ranking(score_b)},
        "C_own_valid_denominator": {"ranking": ranking_c},
        "D_normalized_recoverable_replies": {"denominator": len(common_d), "scores": score_d, "ranking": ranking(score_d)},
    }
    orders = {name: [row["model"] for row in p["ranking"]] for name, p in policies.items()}
    primary = orders["A_common_valid"]
    consistent = all(order == primary for order in orders.values())
    report = {
        "schema": "personal-agent-api-sensitivity-v1", "tag": TAG,
        "expected_items": len(allkeys), "primary_common_items": len(common_a),
        "normalized_recovered_items": len(recovered), "recovered_detail": recovered,
        "policies": policies, "rank_order_consistent": consistent,
        "primary_order": primary,
        "note": "Policy B is a stress test only; the published ranking is A. Invalid items are never scored as failures.",
    }
    (ROOT / "docs" / f"{TAG}-sensitivity.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"rank_order_consistent": consistent,
                      "primary_order": [DISPLAY[m] for m in primary],
                      "policies": {k: [DISPLAY[x] for x in v] for k, v in orders.items()}},
                     ensure_ascii=False, indent=2))
    return 0 if consistent else 1


if __name__ == "__main__":
    raise SystemExit(main())
