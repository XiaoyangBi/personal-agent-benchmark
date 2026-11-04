#!/usr/bin/env python3
"""Run one API model across persona bundles with technical-only resume/retry.

No response is selected by score. The first technically valid response for a
(cp, condition) key is retained; later attempts only fill missing or invalid keys.
"""

import argparse
import importlib.util
import json
import subprocess
import sys
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER_DIR = ROOT / "persona-01-linzhou" / "runner"
RUNNER = RUNNER_DIR / "runner.py"
CONDITIONS = ("C0", "C1", "C2", "C3")
sys.path.insert(0, str(RUNNER_DIR))


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner_lib = load_module("suite_runner", RUNNER)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def valid_run(run):
    reply = run.get("reply") or {}
    if reply.get("error") or not isinstance(reply.get("text"), str):
        return False
    if any(not isinstance(reply.get(key), list) for key in ("payload", "citations", "tool_calls")):
        return False
    if not reply["text"].strip() and not reply["tool_calls"]:
        return False
    return (run.get("score") or {}).get("passed") is not None


def atomic_write(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def attempt_number(path):
    match = re.search(r"-attempt(\d+)\.json$", path.name)
    return int(match.group(1)) if match else 0


def merge_attempt(final, attempt):
    """Merge technical completions only; never replace a valid run by score."""
    runs = {(r["cp"], r["condition"]): r for r in final.get("runs", [])}
    matrix = final.get("matrix", {})
    for run in attempt.get("runs", []):
        key = (run["cp"], run["condition"])
        old = runs.get(key)
        if old is not None and valid_run(old):
            continue
        runs[key] = run
        cid, condition = key
        source_row = attempt.get("matrix", {}).get(cid, {})
        if condition in source_row:
            matrix.setdefault(cid, {})[condition] = source_row[condition]
    final["runs"] = [runs[key] for key in sorted(runs)]
    final["matrix"] = matrix
    return sum(1 for run in attempt.get("runs", []) if valid_run(run))


def rebuild_matrix(final, persona, specs):
    cp_map = {cp["id"]: cp for cp in persona["checkpoints"]}
    for cid, row in final.get("matrix", {}).items():
        evidence = specs[cid].get("evidence", [])
        c3_ids = row.get("C3", {}).get("context", {}).get("ids", [])
        retrieval = {
            "evidence": evidence,
            "retrieved": [x for x in c3_ids if x != cid and x != cp_map[cid]["session"]],
            "hit": bool(set(evidence) & set(c3_ids)) if evidence and "C3" in row else False,
            "missing": [x for x in evidence if x not in c3_ids],
        }
        row["retrieval"] = retrieval
        run_map = {(r["cp"], r["condition"]): r for r in final["runs"]}
        if all((cid, condition) in run_map and valid_run(run_map[(cid, condition)]) for condition in CONDITIONS):
            row["attribution"] = runner_lib.attribution(cp_map[cid], row, retrieval)
        else:
            row.pop("attribution", None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--tag", default="api-v1", help="Result filename prefix; use a new tag for a new decoding protocol")
    parser.add_argument("--model-config", required=True)
    parser.add_argument("--personas", default="", help="Comma-separated directory names; default all ten")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--no-thinking", action="store_true")
    parser.add_argument("--targeted", action="store_true",
                        help="Use --retry-from on existing results so only invalid (cp, condition) keys are called")
    args = parser.parse_args()

    persona_roots = sorted(p for p in ROOT.glob("persona-*") if p.is_dir() and (p / "data").is_dir())
    if args.personas:
        wanted = set(args.personas.split(","))
        persona_roots = [p for p in persona_roots if p.name in wanted]
    if len(persona_roots) != (10 if not args.personas else len(set(args.personas.split(",")))):
        raise SystemExit("Persona selection did not resolve to the requested directories")

    suite = {"schema": "personal-agent-api-suite-v1", "tag": args.tag, "model": args.model, "personas": []}
    for persona_root in persona_roots:
        data_files = sorted((persona_root / "data").glob("persona-*.json"))
        persona = read(data_files[0])
        specs = read(persona_root / "data" / "assertions.json")
        expected = {(cp["id"], condition) for cp in persona["checkpoints"] for condition in CONDITIONS}
        results = persona_root / "results"
        prefix = f"{args.tag}-{args.model}"
        final_path = results / f"{prefix}.json"
        final = read(final_path) if final_path.exists() else {
            "meta": {
                "persona": persona["persona_id"], "persona_file": data_files[0].name,
                "mode": "api", "model": args.model, "budget": 8000,
                "conditions": list(CONDITIONS), "scoring_spec": "assertions.json",
                "max_tokens": args.max_tokens, "workers": args.workers,
                "no_thinking": bool(args.no_thinking), "tag": args.tag,
                "merged_from_attempts": True,
            },
            "runs": [], "matrix": {},
        }

        # The resumed invocation's decoding protocol is authoritative for new calls.
        final["meta"].update({
            "model": args.model, "max_tokens": args.max_tokens,
            "workers": args.workers, "no_thinking": bool(args.no_thinking),
            "tag": args.tag, "scoring_spec": "assertions.json",
        })

        # Recover any attempts left by an interrupted earlier suite invocation.
        attempts = sorted(results.glob(f"{prefix}-attempt*.json"), key=attempt_number)
        for attempt_path in attempts:
            merge_attempt(final, read(attempt_path))
        final["meta"]["attempt_files"] = [p.name for p in attempts]
        rebuild_matrix(final, persona, specs)
        atomic_write(final_path, final)

        first_new_attempt = max((attempt_number(path) for path in attempts), default=0) + 1
        for attempt_no in range(first_new_attempt, first_new_attempt + args.attempts):
            valid_keys = {key for key in expected if any(r["cp"] == key[0] and r["condition"] == key[1] and valid_run(r) for r in final["runs"])}
            incomplete_cps = sorted({cid for cid, _ in expected - valid_keys})
            if not incomplete_cps:
                break
            attempt_path = results / f"{prefix}-attempt{attempt_no}.json"
            command = [
                sys.executable, str(RUNNER), "--persona-root", str(persona_root),
                "--model-config", args.model_config, "--model", args.model,
                "--workers", str(args.workers), "--max-tokens", str(args.max_tokens),
                "--out", attempt_path.name,
            ]
            if args.targeted and final["runs"]:
                command += ["--retry-from", final_path.name]
            else:
                command += ["--checkpoints", ",".join(incomplete_cps), "--conditions", ",".join(CONDITIONS)]
            if args.no_thinking:
                command.append("--no-thinking")
            print(f"START {persona_root.name} attempt={attempt_no} checkpoints={len(incomplete_cps)}", flush=True)
            completed = subprocess.run(command, capture_output=True, text=True)
            if completed.returncode != 0:
                print(completed.stdout[-5000:], flush=True)
                print(completed.stderr[-3000:], file=sys.stderr, flush=True)
                raise SystemExit(completed.returncode)
            if not attempt_path.exists():
                raise SystemExit(f"Runner did not create {attempt_path}")
            merge_attempt(final, read(attempt_path))
            if attempt_path.name not in final["meta"].setdefault("attempt_files", []):
                final["meta"]["attempt_files"].append(attempt_path.name)
            rebuild_matrix(final, persona, specs)
            valid_count = sum(valid_run(r) for r in final["runs"])
            final["meta"]["valid_items"] = valid_count
            final["meta"]["complete"] = valid_count == 252
            atomic_write(final_path, final)
            print(f"MERGED {persona_root.name} attempt={attempt_no} valid={valid_count}/252", flush=True)
            current_runs = final["runs"]
            if (len(current_runs) == 252 and valid_count == 0
                    and all((r.get("reply") or {}).get("error") for r in current_runs)
                    and not any("429" in (r.get("reply") or {}).get("error", "")
                                or "SSL" in (r.get("reply") or {}).get("error", "")
                                or "Timeout" in (r.get("reply") or {}).get("error", "") for r in current_runs)):
                final["meta"]["complete"] = False
                final["meta"]["valid_items"] = 0
                atomic_write(final_path, final)
                print(f"SYSTEMIC_ERROR {args.model} {persona_root.name}; stop without further paid attempts", flush=True)
                return 1

        rebuild_matrix(final, persona, specs)
        valid_count = sum(valid_run(r) for r in final["runs"])
        error_count = sum(bool((r.get("reply") or {}).get("error")) for r in final["runs"])
        final["meta"].update({
            "valid_items": valid_count, "complete": valid_count == 252,
            "error_items": error_count,
            "coverage": {"with_rules": len({r["cp"] for r in final["runs"] if valid_run(r)}), "total": 63},
        })
        atomic_write(final_path, final)
        status = {"persona": persona["persona_id"], "valid_items": valid_count, "complete": valid_count == 252,
                  "path": str(final_path.relative_to(ROOT)), "attempts": final["meta"].get("attempt_files", [])}
        suite["personas"].append(status)
        atomic_write(results / f"{prefix}-suite.json", suite)
        print(f"DONE {persona_root.name} valid={valid_count}/252", flush=True)

    complete = sum(p["complete"] for p in suite["personas"])
    print(f"SUITE_COMPLETE {args.model} personas={complete}/{len(persona_roots)}", flush=True)
    return 0 if complete == len(persona_roots) else 1


if __name__ == "__main__":
    raise SystemExit(main())
