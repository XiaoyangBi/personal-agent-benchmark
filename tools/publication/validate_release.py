#!/usr/bin/env python3
"""Validate public evaluation completeness and common release invariants."""

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PERSONA = ROOT / "persona-01-linzhou"
RUNTIME = PERSONA / "results" / "gpt-runtime"
TEXT_SUFFIXES = {".json", ".md", ".py", ".txt", ".html", ".log"}
SENSITIVE_PATTERNS = {
    "private_key": re.compile(r"BEGIN (?:RSA|OPENSSH) PRIVATE KEY"),
    "api_secret": re.compile(r"(?:sk|gho|github_pat)_[A-Za-z0-9_-]{12,}"),
    "local_home_path": re.compile("/" + r"Users/[^/\s\"']+"),
    "enterprise_document_url": re.compile(r"https://doc\.weixin\.qq\.com/"),
}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_digest(value) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_json_and_inputs() -> dict:
    json_count = 0
    for path in ROOT.rglob("*.json"):
        read_json(path)
        json_count += 1
    manifest = read_json(RUNTIME / "manifest.json")
    samples = manifest["samples"]
    assert len(samples) == 252
    for sample in samples:
        item = sample["item"]
        input_value = read_json(RUNTIME / "inputs" / f"{item}.json")
        assert canonical_digest(input_value) == sample["input_sha256"]
        for round_name in ("r1", "r2", "r3"):
            reply = read_json(RUNTIME / "replies" / round_name / f"{item}.json")
            assert isinstance(reply["text"], str)
            assert isinstance(reply["payload"], list)
            assert isinstance(reply["citations"], list)
            assert isinstance(reply["tool_calls"], list)
    return {"json_files": json_count, "frozen_inputs": 252, "structured_replies": 756}


def validate_scores() -> dict:
    spec = read_json(PERSONA / "data" / "assertions-v3.json")
    assert len(spec) == 63
    assert sum(len(item["rules"]) for item in spec.values()) == 108
    expected = {"r1": 161, "r2": 155, "r3": 166}
    for round_name, passed in expected.items():
        value = read_json(RUNTIME / f"{round_name}.json")
        assert len(value["runs"]) == 252
        assert value["meta"]["complete"] is True
        assert sum(run["score"]["passed"] for run in value["runs"]) == passed
    stability = read_json(RUNTIME / "stability-three-models.json")
    assert stability["meta"]["common_items"] == 252
    assert stability["meta"]["common_per_condition"] == {key: 63 for key in ("C0", "C1", "C2", "C3")}
    return {"checkpoints": 63, "rules_v3": 108, "gpt_passed_per_round": expected, "common_items": 252}


def validate_sensitive_data() -> None:
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for label, pattern in SENSITIVE_PATTERNS.items():
            assert not pattern.search(text), f"Sensitive pattern {label}: {path.relative_to(ROOT)}"


def main() -> None:
    counts = validate_json_and_inputs()
    scores = validate_scores()
    validate_sensitive_data()
    assert (ROOT / "docs" / "specification.md").is_file()
    assert len(read_json(ROOT / "docs" / "run-inventory.json")) > 0
    print(json.dumps({"status": "pass", **counts, **scores, "sensitive_scan": "pass"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
