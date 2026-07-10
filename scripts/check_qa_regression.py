#!/usr/bin/env python3
"""Validate the structural integrity of the legal QA regression catalogue."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kg_common import load_entities, scalar_text


REQUIRED_FIELDS = {
    "id", "as_of", "question", "expected", "required_authority_ids",
    "required_rule_ids", "forbidden_claims",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--file", type=Path, default=Path("tests/qa_regression.jsonl"))
    args = parser.parse_args()
    root = args.root.resolve()
    path = args.file if args.file.is_absolute() else root / args.file

    entities, parse_issues = load_entities(root)
    if parse_issues:
        print(json.dumps({"ok": False, "parse_issues": parse_issues}, ensure_ascii=False, indent=2))
        return 1
    entity_ids = {scalar_text(entity.data.get("id")) for entity in entities}
    rule_ids = {
        scalar_text(entity.data.get("id"))
        for entity in entities
        if scalar_text(entity.data.get("entity_type")) == "rule"
    }

    issues: list[dict[str, object]] = []
    seen: set[str] = set()
    rows = 0
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not raw_line.strip():
            continue
        rows += 1
        try:
            record = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            issues.append({"line": line_number, "code": "INVALID_JSON", "message": str(exc)})
            continue
        missing = sorted(REQUIRED_FIELDS - set(record))
        if missing:
            issues.append({"line": line_number, "code": "MISSING_FIELDS", "fields": missing})
        record_id = str(record.get("id", ""))
        if not record_id or record_id in seen:
            issues.append({"line": line_number, "code": "DUPLICATE_OR_EMPTY_ID", "id": record_id})
        seen.add(record_id)
        for entity_id in record.get("required_authority_ids", []):
            if entity_id not in entity_ids:
                issues.append({"line": line_number, "code": "UNKNOWN_AUTHORITY_ID", "id": entity_id})
        for rule_id in record.get("required_rule_ids", []):
            if rule_id not in rule_ids:
                issues.append({"line": line_number, "code": "UNKNOWN_RULE_ID", "id": rule_id})

    print(json.dumps({"ok": not issues, "rows": rows, "issues": issues}, ensure_ascii=False, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
