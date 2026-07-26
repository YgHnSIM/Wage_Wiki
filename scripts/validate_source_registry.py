#!/usr/bin/env python3
"""Validate the normalized source registry with Draft 2020-12 JSON Schema."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from kg_common import load_json, write_json, severity_fails
from source_catalog import SourceRegistryError, load_source_registry


def validate(root: Path) -> dict[str, object]:
    try:
        import jsonschema
    except ImportError as exc:
        return {"summary": {"issues": 1}, "issues": [{"severity": "critical", "code": "JSONSCHEMA_DEPENDENCY_MISSING", "path": "requirements-dev.txt", "field": "", "message": str(exc)}]}
    schema_path = root / "schemas" / "source-registry-v1.1.schema.json"
    schema = load_json(schema_path, None)
    try:
        registry = load_source_registry(root)
    except SourceRegistryError as exc:
        return {"summary": {"issues": 1}, "issues": [{"severity": "critical", "code": "SOURCE_REGISTRY_READ", "path": "sources/registry.yaml", "field": "", "message": str(exc)}]}
    validator_cls = jsonschema.validators.validator_for(schema)
    validator_cls.check_schema(schema)
    validator = validator_cls(schema, format_checker=jsonschema.FormatChecker())
    issues = [{"severity": "high", "code": "JSON_SCHEMA_INVALID", "path": "sources/registry.yaml", "field": ".".join(str(item) for item in error.absolute_path), "message": error.message} for error in validator.iter_errors(registry)]
    return {"schema_version": "1.1", "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "summary": {"records": len(registry.get("sources", [])) if isinstance(registry.get("sources"), list) else 0, "issues": len(issues)}, "issues": issues}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fail-on", choices=("critical", "high", "medium", "low", "info", "none"), default="high")
    args = parser.parse_args(argv)
    report = validate(args.root.resolve())
    write_json(report, args.output)
    issues = report.get("issues", [])
    return 1 if severity_fails(issues, args.fail_on) else 0


if __name__ == "__main__":
    sys.exit(main())
