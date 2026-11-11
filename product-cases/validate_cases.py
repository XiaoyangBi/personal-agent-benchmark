#!/usr/bin/env python3
"""Validate the shipped white-box product case layer.

Run from the repository root:

    python3 product-cases/validate_cases.py

The check is deliberately dependency free: it interprets the small subset of
JSON Schema used by `product-cases/schema/`, then adds the invariants a schema
cannot express (cross references, grid coverage, redaction).
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SCHEMA = ROOT / "schema"

TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
}

# Identifiers that must never appear in published data: staff names, working
# nicknames, the operator's own products and internal document paths.
FORBIDDEN = [
    "谢扬", "马小艺", "诗洋", "志建", "许凡", "Yafei", "Fan Xu", "芃芃", "小艺", "Zhijian",
    "Eazo", "Instinct", "Fellou", "reports/",
]
LEAK_PATTERNS = {
    "url": re.compile(r"https?://|www\."),
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    "phone": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
}

errors: list[str] = []
warnings: list[str] = []


def fail(message: str) -> None:
    errors.append(message)


def load(name: str):
    path = DATA / name
    if not path.is_file():
        fail(f"missing data file {name}")
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"{name} is not valid JSON: {exc}")
        return []


def check_schema(record: dict, schema: dict, where: str) -> None:
    for key in schema.get("required", []):
        if key not in record:
            fail(f"{where}: missing required field {key}")
    props = schema.get("properties", {})
    for key, spec in props.items():
        if key not in record:
            continue
        value = record[key]
        expected = spec.get("type")
        if expected and not isinstance(value, TYPES[expected]):
            fail(f"{where}: {key} should be {expected}, got {type(value).__name__}")
            continue
        if "enum" in spec and value not in spec["enum"]:
            fail(f"{where}: {key} = {value!r} not in {spec['enum']}")
        if "pattern" in spec and isinstance(value, str) and not re.search(spec["pattern"], value):
            fail(f"{where}: {key} = {value!r} does not match {spec['pattern']}")
        if "minLength" in spec and isinstance(value, str) and len(value) < spec["minLength"]:
            fail(f"{where}: {key} shorter than {spec['minLength']}")
        if expected == "array" and "items" in spec and isinstance(value, list):
            item_type = spec["items"].get("type")
            if item_type:
                for item in value:
                    if not isinstance(item, TYPES[item_type]):
                        fail(f"{where}: {key} has a non-{item_type} item")
    if schema.get("additionalProperties") is False:
        extra = set(record) - set(props)
        if extra:
            fail(f"{where}: unexpected fields {sorted(extra)}")


def main() -> int:
    cases = load("cases.json")
    questions = load("questions.json")
    role_cards = load("role-cards.json")
    taxonomy = load("taxonomy.json")
    segments = load("segments.json")
    need_units = load("need-units.json")
    value_goals = load("value-goals.json")
    capabilities = load("capabilities.json")
    review_rules = load("review-rules.json")
    scoring_rules = load("scoring-rules.json")
    refusal = load("refusal-matrix.json")
    scale = load("counterpart-scale.json")

    if errors:
        report()
        return 1

    # ---- schema conformance -------------------------------------------------
    case_schema = json.loads((SCHEMA / "case.schema.json").read_text(encoding="utf-8"))
    question_schema = json.loads((SCHEMA / "question.schema.json").read_text(encoding="utf-8"))
    role_schema = json.loads((SCHEMA / "role-card.schema.json").read_text(encoding="utf-8"))

    for case in cases:
        check_schema(case, case_schema, f"case {case.get('case_id')}")
    for question in questions:
        check_schema(question, question_schema, f"question {question.get('question_id')}")
    for card in role_cards:
        check_schema(card, role_schema, f"role card {card.get('role_card_id')}")

    # ---- identity -----------------------------------------------------------
    case_ids = Counter(c.get("case_id") for c in cases)
    for case_id, count in case_ids.items():
        if count > 1:
            fail(f"duplicate case_id {case_id} ({count})")
    question_ids = Counter(q.get("question_id") for q in questions)
    for question_id, count in question_ids.items():
        if count > 1:
            fail(f"duplicate question_id {question_id} ({count})")
    card_ids = {c.get("role_card_id") for c in role_cards}

    known_cases = set(case_ids)
    for question in questions:
        case_id = question.get("case_id")
        if case_id not in known_cases:
            fail(f"question {question['question_id']} points at unknown case {case_id}")

    for case in cases:
        for question_id in case.get("question_ids") or []:
            if question_id not in question_ids:
                fail(f"case {case['case_id']} lists unknown question {question_id}")
        for capability in case.get("capabilities") or []:
            if capability.split(" ")[0] not in {c.get("capability_id") for c in capabilities}:
                fail(f"case {case['case_id']} references unknown capability {capability}")

    # A question and its case must agree about the case id.
    case_of_question = {q["question_id"]: q.get("case_id") for q in questions}
    for case in cases:
        for question_id in case.get("question_ids") or []:
            if question_id in case_of_question and case_of_question[question_id] != case["case_id"]:
                fail(f"question {question_id} claims case {case_of_question[question_id]}, "
                     f"but case {case['case_id']} lists it")

    # ---- taxonomy -----------------------------------------------------------
    level1 = {e["code"] for e in taxonomy.get("level1", [])}
    level2 = {e["code"]: e for e in taxonomy.get("level2", [])}
    if len(level1) != 11:
        fail(f"taxonomy should carry 11 level-1 domains, found {len(level1)}")
    if len(level2) != 97:
        fail(f"taxonomy should carry 97 level-2 domains, found {len(level2)}")
    for code, entry in level2.items():
        if entry.get("level1_code") not in level1:
            fail(f"domain {code} references unknown level-1 code {entry.get('level1_code')}")
        if not entry.get("in_scope"):
            fail(f"domain {code} has no in_scope boundary")
        if not entry.get("out_of_scope"):
            fail(f"domain {code} has no out_of_scope redirect")
        if len(entry.get("need_examples") or []) < 2:
            fail(f"domain {code} has fewer than two need examples")

    # ---- persona bridge -----------------------------------------------------
    links_path = ROOT / "persona-links.json"
    if not links_path.is_file():
        fail("missing persona-links.json")
    else:
        links = json.loads(links_path.read_text(encoding="utf-8"))
        seen_personas = set()
        for entry in links.get("personas", []):
            persona = entry.get("persona")
            if persona in seen_personas:
                fail(f"persona {persona} linked twice")
            seen_personas.add(persona)
            if not (ROOT.parent / persona).is_dir():
                fail(f"persona directory {persona} does not exist")
            for item in entry.get("cases", []):
                if item.get("case_id") not in known_cases:
                    fail(f"{persona} links unknown case {item.get('case_id')}")
                if item.get("domain_code") not in level2:
                    fail(f"{persona} uses unknown domain {item.get('domain_code')}")
                if item.get("role_card") and item["role_card"] not in card_ids:
                    fail(f"{persona} links unknown role card {item['role_card']}")
                for question_id in item.get("question_ids") or []:
                    if question_id not in question_ids:
                        fail(f"{persona} links unknown question {question_id}")
        if len(seen_personas) != 10:
            fail(f"expected 10 linked personas, found {len(seen_personas)}")

    # ---- review instruments -------------------------------------------------
    intensities = {r.get("refusal_intensity") for r in refusal}
    necessities = {r.get("goal_necessity") for r in refusal}
    if len(refusal) != len(intensities) * len(necessities):
        fail("refusal matrix has holes: every intensity x necessity cell must be filled")
    if len(scale) != 5:
        fail(f"counterpart scale should have 5 dimensions, found {len(scale)}")
    if len(segments) < 30:
        fail(f"segment list looks truncated ({len(segments)})")
    if len(value_goals) < 40:
        fail(f"value goal list looks truncated ({len(value_goals)})")
    if len(review_rules) < 20:
        fail(f"review rule list looks truncated ({len(review_rules)})")

    # ---- question grid ------------------------------------------------------
    full = [q for q in questions if q.get("spec_completeness") == "完整规格"]
    grid = defaultdict(int)
    for question in full:
        grid[(question.get("purpose"), question.get("relation"))] += 1
    purposes = {e["code"] for e in taxonomy.get("purposes", [])}
    relations = {e["code"] for e in taxonomy.get("relations", [])}
    if purposes and relations:
        expected_cells = {(p, r) for p in purposes for r in relations}
        missing = expected_cells - set(grid)
        if missing:
            fail(f"question grid misses {len(missing)} of {len(expected_cells)} cells")
        uneven = {cell: n for cell, n in grid.items() if n != 7}
        if uneven:
            warnings.append(f"question grid cells without exactly 7 questions: {uneven}")
    status = Counter(q.get("spec_completeness") for q in questions)
    no_stopped = sum(1 for q in full if not q.get("verdict_stopped"))
    if no_stopped:
        warnings.append(f"{no_stopped}/{len(full)} full-spec questions lack a 得体止步 verdict")

    # ---- redaction ----------------------------------------------------------
    for name in ("cases.json", "questions.json", "role-cards.json", "segments.json",
                 "need-units.json", "review-rules.json", "scoring-rules.json",
                 "capabilities.json", "taxonomy.json", "value-goals.json",
                 "refusal-matrix.json", "counterpart-scale.json"):
        text = (DATA / name).read_text(encoding="utf-8")
        for token in FORBIDDEN:
            if token in text:
                fail(f"{name} still contains forbidden token {token}")
        for label, pattern in LEAK_PATTERNS.items():
            hit = pattern.search(text)
            if hit:
                fail(f"{name} contains a {label}: {hit.group(0)[:60]}")

    # ---- summary ------------------------------------------------------------
    print(f"cases          {len(cases):5d}  (curated {sum(1 for c in cases if c['curation'] == 'curated')})")
    print(f"questions      {len(questions):5d}  (full spec {len(full)}, {len(grid)} grid cells)")
    print(f"role cards     {len(role_cards):5d}")
    print(f"segments       {len(segments):5d}")
    print(f"need units     {len(need_units):5d}")
    print(f"value goals    {len(value_goals):5d}")
    print(f"capabilities   {len(capabilities):5d}")
    print(f"review rules   {len(review_rules):5d}")
    print(f"scoring rules  {len(scoring_rules):5d}")
    print(f"refusal cells  {len(refusal):5d}")
    print(f"scale dims     {len(scale):5d}")
    print(f"domains        {len(level2):5d} level-2 over {len(level1)} level-1")
    print(f"question status {dict(status)}")
    report()
    return 1 if errors else 0


def report() -> None:
    for warning in warnings:
        print(f"WARN  {warning}")
    for error in errors:
        print(f"ERROR {error}")
    if errors:
        print(f"\n{len(errors)} error(s)")
    else:
        print(f"\nOK: {len(warnings)} warning(s), 0 errors")


if __name__ == "__main__":
    sys.exit(main())
