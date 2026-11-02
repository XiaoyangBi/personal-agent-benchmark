#!/usr/bin/env python3
"""Validate persona-02..10 data, rubric solvability and optional dry-run outputs."""

import argparse
import importlib.util
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "persona-01-linzhou" / "runner"
EXPECTED_SESSIONS = {f"S{i:02d}" for i in range(1, 24)}
EXPECTED_CPS = {f"CP{i:02d}" for i in range(1, 64)}
CONDITIONS = ("C0", "C1", "C2", "C3")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


assertions_engine = load_module("persona_assertions", RUNNER / "assertions.py")
conditions = load_module("persona_conditions", RUNNER / "conditions.py")
memory_module = load_module("persona_memory", RUNNER / "memory.py")


def valid_reply(reply):
    if not isinstance(reply, dict) or not isinstance(reply.get("text"), str):
        return False
    if any(not isinstance(reply.get(key), list) for key in ("payload", "citations", "tool_calls")):
        return False
    return all(
        isinstance(call, dict) and isinstance(call.get("tool"), str) and isinstance(call.get("params"), dict)
        for call in reply["tool_calls"]
    )


def validate_persona(root, require_dry_run):
    errors = []
    data_files = sorted((root / "data").glob("persona-*.json"))
    if len(data_files) != 1:
        return {"persona": root.name, "errors": [f"expected one persona file, got {len(data_files)}"]}
    data = json.loads(data_files[0].read_text(encoding="utf-8"))
    sessions_doc = json.loads((root / "data" / "sessions.json").read_text(encoding="utf-8"))
    sessions = sessions_doc["sessions"]
    specs = json.loads((root / "data" / "assertions.json").read_text(encoding="utf-8"))
    fixtures = json.loads((root / "data" / "dry_run_replies.json").read_text(encoding="utf-8"))
    cps = {cp["id"]: cp for cp in data["checkpoints"]}

    if set(sessions) != EXPECTED_SESSIONS:
        errors.append("session set is not S01..S23")
    if set(cps) != EXPECTED_CPS or set(specs) != EXPECTED_CPS:
        errors.append("checkpoint/spec set is not CP01..CP63")
    if sessions_doc.get("persona_id") != data.get("persona_id"):
        errors.append("persona id mismatch between data and sessions")
    if not data.get("synthetic") or not sessions_doc.get("synthetic"):
        errors.append("synthetic marker missing")
    dims = Counter(cp["dim"] for cp in cps.values())
    if dims != {f"D{i}": 9 for i in range(1, 8)}:
        errors.append(f"dimension distribution invalid: {dict(dims)}")
    for sid, session in sessions.items():
        if not session.get("turns") or any(not isinstance(t, str) or not t.strip() for t in session["turns"]):
            errors.append(f"{sid} has empty turns")
        if re.search(r"CP\d+|PB\d+|PK\d+|PJ\d+|期望行为|标准答案", session.get("title", "")):
            errors.append(f"{sid} title leaks evaluation metadata")

    plant_ids = set()
    for plant in data.get("plants", []):
        pid = plant["id"]
        if pid in plant_ids:
            errors.append(f"duplicate plant {pid}")
        plant_ids.add(pid)
        source = plant["input_session"]
        keyword = plant["keyword"]
        allowed = set(plant["allowed_sessions"])
        if source not in allowed or source not in sessions:
            errors.append(f"{pid} invalid source/allowlist")
            continue
        if keyword not in "\n".join(sessions[source]["turns"]):
            errors.append(f"{pid} keyword absent from declared source {source}")
        for sid, session in sessions.items():
            if sid not in allowed and keyword in "\n".join(session["turns"]):
                errors.append(f"{pid} keyword leaks into unauthorized {sid}")
        for cp in plant.get("checkpoints", []):
            if cp not in cps:
                errors.append(f"{pid} references unknown {cp}")

    context_items = 0
    oracle_fixture_passes = 0
    for cid, cp in cps.items():
        spec = specs[cid]
        sid = cp["session"]
        turn = spec.get("turn")
        if sid not in sessions:
            errors.append(f"{cid} invalid current session {sid}")
            continue
        if not isinstance(turn, int) or not 1 <= turn <= len(sessions[sid]["turns"]):
            errors.append(f"{cid} invalid turn {turn}")
            continue
        if sessions[sid]["turns"][turn - 1] != spec.get("trigger"):
            errors.append(f"{cid} trigger not exact at declared turn")
        for evidence in spec.get("evidence", []):
            if evidence not in sessions:
                errors.append(f"{cid} unknown evidence {evidence}")
            elif int(evidence[1:]) > int(sid[1:]):
                errors.append(f"{cid} future evidence {evidence}>{sid}")
        if not spec.get("rules"):
            errors.append(f"{cid} has no rules")

        fixture = fixtures.get(cid)
        if not valid_reply(fixture):
            errors.append(f"{cid} invalid fixture reply schema")
        else:
            score = assertions_engine.evaluate(fixture, spec["rules"])
            if score["passed"] is not True:
                failed = [d["msg"] for d in score["details"] if not d["ok"]]
                errors.append(f"{cid} fixture fails its rubric: {failed}")
            else:
                oracle_fixture_passes += 1

        memory = memory_module.NaiveMemory()
        for memory_sid in sorted(sessions, key=conditions.sid_index):
            memory.insert(memory_sid, "\n".join(sessions[memory_sid]["turns"]), conditions.sid_index(memory_sid))
        for condition in CONDITIONS:
            cp_view = {**cp, "evidence": spec.get("evidence", [])}
            ctx = conditions.build(cp_view, condition, sessions, memory, 8000, spec["trigger"], turn)
            context_items += 1
            if ctx["turn"] != turn:
                errors.append(f"{cid}/{condition} wrong resolved turn")
            if spec["trigger"] in ctx["text"]:
                errors.append(f"{cid}/{condition} leaks current trigger into history")
            if any(int(item[1:]) > int(sid[1:]) for item in ctx["ids"]):
                errors.append(f"{cid}/{condition} includes future session")
            if condition == "C0" and ctx["ids"] != [sid]:
                errors.append(f"{cid}/C0 includes non-current sessions")
            if condition == "C1" and not set(spec.get("evidence", [])) <= set(ctx["ids"]):
                errors.append(f"{cid}/C1 misses oracle evidence")
            messages = conditions.build_messages("system", ctx, spec["trigger"], "hint", spec.get("env", ""))
            if data["canary"] in messages[1]["content"]:
                errors.append(f"{cid}/{condition} canary leaked into model input")
            if messages[1]["content"].count(spec["trigger"]) < 1:
                errors.append(f"{cid}/{condition} trigger absent from model message")

    serialized_sessions = json.dumps(sessions_doc, ensure_ascii=False)
    if data["canary"] in serialized_sessions:
        errors.append("canary appears in sessions")

    dry_run = {"required": require_dry_run, "status": "not_checked"}
    result_path = root / "results" / "dry-run.json"
    if require_dry_run:
        if not result_path.exists():
            errors.append("dry-run.json missing")
        else:
            result = json.loads(result_path.read_text(encoding="utf-8"))
            runs = result.get("runs", [])
            keys = [(r.get("cp"), r.get("condition")) for r in runs]
            if len(runs) != 252 or len(set(keys)) != 252 or set(keys) != {(cp, cond) for cp in EXPECTED_CPS for cond in CONDITIONS}:
                errors.append("dry-run does not contain exactly 252 unique cp/condition items")
            if result.get("meta", {}).get("mode") != "dry_run" or result.get("meta", {}).get("model") != "fixture":
                errors.append("dry-run metadata invalid")
            if result.get("meta", {}).get("persona") != data["persona_id"]:
                errors.append("dry-run persona mismatch")
            if result.get("meta", {}).get("scoring_spec") != "assertions.json":
                errors.append("dry-run scoring spec not recorded")
            for run in runs:
                reply = run.get("reply", {})
                if not valid_reply(reply) or reply.get("error"):
                    errors.append(f"invalid dry-run reply at {run.get('cp')}/{run.get('condition')}")
                    break
            if set(result.get("matrix", {})) != EXPECTED_CPS:
                errors.append("dry-run matrix incomplete")
            for cid, row in result.get("matrix", {}).items():
                if not set(CONDITIONS) <= set(row) or "attribution" not in row:
                    errors.append(f"dry-run matrix invalid at {cid}")
                    break
            dry_run = {"required": True, "status": "checked", "runs": len(runs), "unique_items": len(set(keys))}

    return {
        "persona": data["persona_id"], "sessions": len(sessions),
        "turns": sum(len(s["turns"]) for s in sessions.values()),
        "checkpoints": len(cps), "rules": sum(len(s["rules"]) for s in specs.values()),
        "plants": len(data.get("plants", [])), "trap_checkpoints": sum(cp["trap"] for cp in cps.values()),
        "context_items_checked": context_items, "oracle_fixtures_passed": oracle_fixture_passes,
        "dry_run": dry_run, "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-dry-run", action="store_true")
    args = parser.parse_args()
    roots = sorted(p for p in ROOT.glob("persona-*") if p.is_dir() and not p.name.startswith("persona-01-"))
    if len(roots) != 9:
        raise SystemExit(f"Expected nine expansion personas, found {len(roots)}")
    reports = [validate_persona(root, args.require_dry_run) for root in roots]

    # Exact trigger duplication is a diversity signal, not a model-quality score.
    trigger_sets = []
    for root in roots:
        specs = json.loads((root / "data" / "assertions.json").read_text(encoding="utf-8"))
        trigger_sets.append({spec["trigger"] for spec in specs.values()})
    pairwise = []
    for i, left in enumerate(roots):
        for j in range(i + 1, len(roots)):
            right = roots[j]
            shared = len(trigger_sets[i] & trigger_sets[j])
            pairwise.append({"a": left.name, "b": right.name, "identical_triggers": shared})

    output = {
        "schema": "personal-agent-expansion-validation-v1",
        "model_calls": 0,
        "status": "pass" if all(not r["errors"] for r in reports) else "fail",
        "totals": {
            "personas": len(reports), "sessions": sum(r["sessions"] for r in reports),
            "checkpoints": sum(r["checkpoints"] for r in reports),
            "rules": sum(r["rules"] for r in reports),
            "context_items": sum(r["context_items_checked"] for r in reports),
            "dry_run_items": sum(r["dry_run"].get("runs", 0) for r in reports),
        },
        "diversity": {
            "metric": "exact identical trigger count per persona pair; shared generic prompts are allowed and reported",
            "pairs": pairwise,
        },
        "interpretation": "Structural, anti-leakage, rubric-fixture and fixture transport checks only. No paid model was called and no model performance is claimed.",
        "personas": reports,
    }
    path = ROOT / "docs" / "persona-validation.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": output["status"], "totals": output["totals"],
                      "errors": {r["persona"]: r["errors"] for r in reports if r["errors"]}}, ensure_ascii=False, indent=2))
    return 0 if output["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
