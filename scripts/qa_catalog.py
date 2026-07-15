#!/usr/bin/env python3
"""Shared validation for the legal QA regression catalogue."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from kg_common import Entity, parse_date, scalar_text


REQUIRED_FIELDS = frozenset(
    {
        "id",
        "as_of",
        "question",
        "expected",
        "required_authority_ids",
        "required_rule_ids",
        "forbidden_claims",
    }
)


def _catalog_issue(line: int, code: str, message: str, **details: Any) -> dict[str, Any]:
    return {"line": line, "code": code, "message": message, **details}


def _is_string_list(value: Any, *, allow_empty: bool = True) -> bool:
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and all(isinstance(item, str) and bool(item.strip()) for item in value)
    )


def validate_qa_catalog(
    path: Path,
    id_targets: Mapping[str, Entity],
    *,
    missing_ok: bool = False,
) -> dict[str, Any]:
    """Validate QA JSONL syntax, field types, dates, and entity references."""

    issues: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except FileNotFoundError:
        if missing_ok:
            return {"rows": 0, "issues": []}
        return {
            "rows": 0,
            "issues": [_catalog_issue(0, "QA_READ", f"catalogue does not exist: {path}")],
        }
    except (OSError, UnicodeError) as exc:
        return {"rows": 0, "issues": [_catalog_issue(0, "QA_READ", str(exc))]}

    seen: set[str] = set()
    rows = 0
    for line_number, raw_line in enumerate(lines, start=1):
        if not raw_line.strip():
            continue
        rows += 1
        try:
            record = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            issues.append(_catalog_issue(line_number, "INVALID_JSON", exc.msg))
            continue
        if not isinstance(record, dict):
            issues.append(
                _catalog_issue(line_number, "INVALID_RECORD_TYPE", "record must be an object")
            )
            continue

        missing = sorted(REQUIRED_FIELDS - set(record))
        if missing:
            issues.append(
                _catalog_issue(
                    line_number,
                    "MISSING_FIELDS",
                    f"missing required fields: {missing}",
                    fields=missing,
                )
            )

        record_id = scalar_text(record.get("id"))
        if not record_id or record_id in seen:
            issues.append(
                _catalog_issue(
                    line_number,
                    "DUPLICATE_OR_EMPTY_ID",
                    "test id is missing or duplicated",
                    id=record_id,
                )
            )
        if record_id:
            seen.add(record_id)

        if not parse_date(record.get("as_of")):
            issues.append(
                _catalog_issue(line_number, "INVALID_AS_OF", "as_of must be a valid YYYY-MM-DD date")
            )

        for field, expected_type in (
            ("required_authority_ids", "authority"),
            ("required_rule_ids", "rule"),
        ):
            values = record.get(field)
            if not _is_string_list(values):
                issues.append(
                    _catalog_issue(
                        line_number,
                        "INVALID_ID_LIST",
                        f"{field} must be a list of non-empty strings",
                        field=field,
                    )
                )
                continue
            for required_id in values:
                target = id_targets.get(required_id)
                if target is None:
                    code = "UNKNOWN_RULE_ID" if expected_type == "rule" else "UNKNOWN_AUTHORITY_ID"
                    issues.append(
                        _catalog_issue(
                            line_number,
                            code,
                            f"unknown required ID: {required_id}",
                            id=required_id,
                            field=field,
                        )
                    )
                elif expected_type == "rule" and scalar_text(target.data.get("entity_type")) != "rule":
                    issues.append(
                        _catalog_issue(
                            line_number,
                            "REQUIRED_ID_NOT_RULE",
                            f"required ID is not a rule: {required_id}",
                            id=required_id,
                            field=field,
                        )
                    )

        forbidden = record.get("forbidden_claims")
        if not _is_string_list(forbidden, allow_empty=False):
            issues.append(
                _catalog_issue(
                    line_number,
                    "INVALID_FORBIDDEN_CLAIMS",
                    "forbidden_claims must be a non-empty list of strings",
                    field="forbidden_claims",
                )
            )

    return {"rows": rows, "issues": issues}
