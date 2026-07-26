#!/usr/bin/env python3
"""Run the Draft 2020-12 validator against every wiki entity.

The repository's semantic linter remains responsible for cross-file checks
(source IDs, relation targets, claim anchors, and legal policy).  This command
is deliberately a small, standard JSON Schema gate so type/format/closed
object errors cannot be hidden by the semantic linter.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import Any

from kg_common import CURRENT_SCHEMA_VERSION, LEGACY_SCHEMA_VERSION, load_entities, load_json, severity_fails, write_json


def _issue(path: str, error: Any) -> dict[str, Any]:
    location = ".".join(str(item) for item in error.absolute_path)
    return {
        "severity": "high",
        "code": "JSON_SCHEMA_INVALID",
        "path": path,
        "field": location,
        "message": error.message,
    }


def validate_frontmatter(root: Path, version: str = CURRENT_SCHEMA_VERSION) -> dict[str, Any]:
    try:
        import jsonschema
    except ImportError as exc:  # pragma: no cover - exercised in minimal installs
        return {
            "schema_version": version,
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "summary": {"entities": 0, "issues": 1, "by_severity": {"critical": 1, "high": 0, "medium": 0, "low": 0, "info": 0}},
            "issues": [{"severity": "critical", "code": "JSONSCHEMA_DEPENDENCY_MISSING", "path": "requirements-dev.txt", "field": "", "message": str(exc)}],
        }

    schema_path = root / "schemas" / f"frontmatter-v{version}.schema.json"
    schema = load_json(schema_path, None)
    if not isinstance(schema, dict):
        return {
            "schema_version": version,
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "summary": {"entities": 0, "issues": 1, "by_severity": {"critical": 1, "high": 0, "medium": 0, "low": 0, "info": 0}},
            "issues": [{"severity": "critical", "code": "JSON_SCHEMA_MISSING", "path": str(schema_path.relative_to(root)), "field": "", "message": "schema must be a JSON object"}],
        }
    try:
        validator_cls = jsonschema.validators.validator_for(schema)
        validator_cls.check_schema(schema)
        validator = validator_cls(schema, format_checker=jsonschema.FormatChecker())
    except Exception as exc:
        return {
            "schema_version": version,
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "summary": {"entities": 0, "issues": 1, "by_severity": {"critical": 1, "high": 0, "medium": 0, "low": 0, "info": 0}},
            "issues": [{"severity": "critical", "code": "JSON_SCHEMA_INVALID", "path": str(schema_path.relative_to(root)), "field": "", "message": str(exc)}],
        }

    entities, parse_issues = load_entities(root)
    issues = list(parse_issues)
    for entity in entities:
        for error in sorted(validator.iter_errors(entity.data), key=lambda item: list(item.absolute_path)):
            issues.append(_issue(entity.relative_path, error))
    counts = {severity: sum(item.get("severity") == severity for item in issues) for severity in ("critical", "high", "medium", "low", "info")}
    return {
        "schema_version": version,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "root": root.as_posix(),
        "summary": {"entities": len(entities), "issues": len(issues), "by_severity": counts},
        "issues": issues,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--version", choices=(LEGACY_SCHEMA_VERSION, CURRENT_SCHEMA_VERSION), default=CURRENT_SCHEMA_VERSION)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fail-on", choices=("critical", "high", "medium", "low", "info", "none"), default="high")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = validate_frontmatter(args.root.resolve(), args.version)
    write_json(report, args.output)
    return 1 if severity_fails(report["issues"], args.fail_on) else 0


if __name__ == "__main__":
    sys.exit(main())
