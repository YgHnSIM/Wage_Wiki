#!/usr/bin/env python3
"""Check append-only canonical entity ID and path history."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from kg_common import load_entities, load_json, scalar_text, write_json


def current_records(root: Path, first_seen: str) -> list[dict[str, Any]]:
    entities, _ = load_entities(root)
    return [{"id": scalar_text(entity.data.get("id")), "path": entity.relative_path, "first_seen": first_seen, "aliases": [scalar_text(item) for item in entity.data.get("id_aliases", []) if scalar_text(item)]} for entity in entities]


def check(root: Path, *, write: bool = False) -> dict[str, Any]:
    path = root / "schemas" / "entity-id-registry.json"
    today = dt.date.today().isoformat()
    current = current_records(root, today)
    existing = load_json(path, {})
    if write and not existing:
        payload = {"format_version": "1.0", "entities": sorted(current, key=lambda item: item["id"])}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        existing = payload
    issues: list[dict[str, Any]] = []
    records = existing.get("entities", []) if isinstance(existing, dict) else []
    by_id = {scalar_text(item.get("id")): item for item in records if isinstance(item, dict) and scalar_text(item.get("id"))}
    for item in current:
        old = by_id.get(item["id"])
        if old is None:
            issues.append({"severity": "high", "code": "ID_REGISTRY_MISSING", "path": str(path.relative_to(root)), "field": "entities", "message": f"canonical ID is not registered: {item['id']}"})
        elif scalar_text(old.get("path")) != item["path"]:
            issues.append({"severity": "critical", "code": "ID_REGISTRY_PATH_CHANGED", "path": str(path.relative_to(root)), "field": item["id"], "message": f"canonical ID path changed: {old.get('path')} -> {item['path']}"})
    current_ids = {item["id"] for item in current}
    for old_id in sorted(set(by_id) - current_ids):
        aliases = by_id[old_id].get("aliases", []) if isinstance(by_id[old_id], dict) else []
        if not aliases:
            issues.append({"severity": "high", "code": "ID_REGISTRY_REMOVED", "path": str(path.relative_to(root)), "field": old_id, "message": "registered canonical ID disappeared without an alias"})
    return {"summary": {"current": len(current), "registered": len(by_id), "issues": len(issues)}, "issues": issues}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = check(args.root.resolve(), write=args.write)
    write_json(report, args.output)
    return 1 if report["issues"] else 0


if __name__ == "__main__":
    sys.exit(main())
