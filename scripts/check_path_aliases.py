#!/usr/bin/env python3
"""Validate the append-only raw/wiki path alias registry."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from kg_common import FrontmatterError, _SubsetYamlParser, normalized_ref, write_json


def check(root: Path) -> dict[str, object]:
    path = root / "sources" / "path_aliases.yaml"
    issues: list[dict[str, str]] = []
    try:
        data = _SubsetYamlParser(path.read_text(encoding="utf-8-sig")).parse()
    except (OSError, UnicodeError, FrontmatterError) as exc:
        return {"summary": {"aliases": 0, "issues": 1}, "issues": [{"severity": "critical", "code": "PATH_ALIAS_PARSE", "path": str(path.relative_to(root)), "message": str(exc)}]}
    if scalar := data.get("schema_version"):
        if str(scalar) != "1.0":
            issues.append({"severity": "critical", "code": "PATH_ALIAS_VERSION", "path": str(path.relative_to(root)), "message": "schema_version must be 1.0"})
    aliases = data.get("aliases")
    if not isinstance(aliases, dict):
        issues.append({"severity": "critical", "code": "PATH_ALIAS_TYPE", "path": str(path.relative_to(root)), "message": "aliases must be a mapping"})
        aliases = {}
    normalized = {normalized_ref(str(old)): normalized_ref(str(new)) for old, new in aliases.items()}
    for old, new in normalized.items():
        if not old or not new:
            issues.append({"severity": "high", "code": "PATH_ALIAS_EMPTY", "path": str(path.relative_to(root)), "message": "alias and target must be nonempty"})
        if not (old.startswith("raw/") or old.startswith("wiki/")) or not (new.startswith("raw/") or new.startswith("wiki/")):
            issues.append({"severity": "high", "code": "PATH_ALIAS_SCOPE", "path": str(path.relative_to(root)), "message": f"alias scope must be raw/ or wiki/: {old} -> {new}"})
    for start in normalized:
        seen: set[str] = set()
        cursor = start
        while cursor in normalized:
            if cursor in seen:
                issues.append({"severity": "critical", "code": "PATH_ALIAS_CYCLE", "path": str(path.relative_to(root)), "message": f"alias cycle detected at {cursor}"})
                break
            seen.add(cursor)
            cursor = normalized[cursor]
    return {"summary": {"aliases": len(normalized), "issues": len(issues)}, "issues": issues}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = check(args.root.resolve())
    write_json(report, args.output)
    return 1 if report["issues"] else 0


if __name__ == "__main__":
    sys.exit(main())
