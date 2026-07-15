#!/usr/bin/env python3
"""Validate the structural integrity of the legal QA regression catalogue."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kg_common import as_list, load_entities, load_json, scalar_text
from qa_catalog import REQUIRED_FIELDS, validate_qa_catalog


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--file", type=Path, default=Path("tests/qa_regression.jsonl"))
    args = parser.parse_args(argv)
    root = args.root.resolve()
    path = args.file if args.file.is_absolute() else root / args.file

    entities, parse_issues = load_entities(root)
    if parse_issues:
        print(json.dumps({"ok": False, "parse_issues": parse_issues}, ensure_ascii=False, indent=2))
        return 1
    id_targets = {}
    by_id = {}
    for entity in entities:
        entity_id = scalar_text(entity.data.get("id"))
        if entity_id:
            by_id[entity_id] = entity
            id_targets[entity_id] = entity
        for alias in as_list(entity.data.get("id_aliases")):
            alias_text = scalar_text(alias)
            if alias_text:
                id_targets.setdefault(alias_text, entity)
    global_aliases = load_json(root / "schemas" / "id-aliases.json", {}).get(
        "aliases_to_canonical", {}
    )
    if isinstance(global_aliases, dict):
        for alias, canonical in global_aliases.items():
            target = by_id.get(scalar_text(canonical))
            if target is not None:
                id_targets.setdefault(scalar_text(alias), target)

    result = validate_qa_catalog(path, id_targets)
    report = {"ok": not result["issues"], **result}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
