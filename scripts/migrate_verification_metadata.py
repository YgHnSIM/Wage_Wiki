#!/usr/bin/env python3
"""Plan or apply additive structured verification metadata migration."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from kg_common import as_list, issue, load_entities, scalar_text, write_json
from migrate_schema_v13 import _ordered, _render_document
from schema_contract import SchemaContractError, load_schema_contract
from verification_contract import (
    LEGACY_VERIFICATION_MAP,
    VERIFICATION_FIELDS,
    VerifierRegistryError,
    legacy_verification_matches,
    load_verifier_registry,
    normalize_legacy_verification,
    validate_verification,
    verification_matches,
)


def _empty_verification_placeholder(value: Any) -> bool:
    """Treat the exact template-shaped empty object as not-yet-populated metadata."""

    if value == {}:
        return True
    if not isinstance(value, dict) or set(value) - VERIFICATION_FIELDS:
        return False
    return (
        value.get("verifier_ids") == []
        and value.get("methods") == []
        and value.get("note") == ""
    )


def migrate_data(
    data: dict[str, Any],
    known_verifier_ids: set[str] | frozenset[str] = frozenset(),
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Map only exact known legacy values and never rewrite verified_by."""

    result = dict(data)
    verified_by = list(as_list(data.get("verified_by")))
    legacy_values = [scalar_text(value) for value in verified_by if scalar_text(value)]
    has_legacy = bool(legacy_values)
    normalized, unmapped = normalize_legacy_verification(verified_by)
    direct_ids = tuple(value for value in unmapped if value in known_verifier_ids)
    unknown = [value for value in unmapped if value not in known_verifier_ids]
    existing = data.get("verification")
    changed = False
    conflict = False
    if direct_ids and (existing is None or _empty_verification_placeholder(existing)):
        # A stable identity does not imply a verification method; require explicit metadata.
        unknown.extend(direct_ids)
    elif direct_ids and not unknown:
        conflict = not isinstance(existing, dict) or not legacy_verification_matches(
            existing,
            normalized,
            direct_ids,
        )
    elif has_legacy and not unknown and (
        existing is None or _empty_verification_placeholder(existing)
    ):
        result["verification"] = normalized
        changed = existing != normalized
    elif existing is not None and has_legacy and not unknown:
        conflict = not isinstance(existing, dict) or not verification_matches(
            existing,
            normalized,
        )
    return _ordered(result), {
        "changed": changed,
        "legacy_values": legacy_values,
        "unknown_legacy_values": list(unknown),
        "existing_metadata_conflict": conflict,
        "verifier_without_last_verified": bool(has_legacy and not scalar_text(data.get("last_verified"))),
        "last_verified_without_verifier": bool(scalar_text(data.get("last_verified")) and not has_legacy),
    }


class MigrationWriteError(RuntimeError):
    """Raised after staged writes fail and any replaced files are restored."""


def _apply_writes_atomically(planned_writes: list[tuple[Any, dict[str, Any], dict[str, Any]]]) -> int:
    staged: list[tuple[Path, Path, bytes, int]] = []
    replaced: list[tuple[Path, bytes, int]] = []
    try:
        for entity, migrated, _ in planned_writes:
            target = entity.path
            original = target.read_bytes()
            mode = target.stat().st_mode
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{target.name}.",
                suffix=".verification-migrate.tmp",
                dir=target.parent,
            )
            temporary = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                    handle.write(_render_document(migrated, entity.body))
                os.chmod(temporary, mode)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
            staged.append((target, temporary, original, mode))

        for target, temporary, original, mode in staged:
            os.replace(temporary, target)
            replaced.append((target, original, mode))
        return len(replaced)
    except Exception as exc:
        rollback_errors: list[str] = []
        for target, original, mode in reversed(replaced):
            restore_name = ""
            try:
                descriptor, restore_name = tempfile.mkstemp(
                    prefix=f".{target.name}.",
                    suffix=".verification-rollback.tmp",
                    dir=target.parent,
                )
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(original)
                os.chmod(restore_name, mode)
                os.replace(restore_name, target)
            except Exception as rollback_exc:
                rollback_errors.append(f"{target}: {rollback_exc}")
                if restore_name:
                    Path(restore_name).unlink(missing_ok=True)
        detail = f"atomic migration write failed: {exc}"
        if rollback_errors:
            detail += "; rollback failed: " + "; ".join(rollback_errors)
        raise MigrationWriteError(detail) from exc
    finally:
        for _, temporary, _, _ in staged:
            temporary.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, help="write migration JSON report; stdout when omitted")
    parser.add_argument("--write", action="store_true", help="apply exact mappings; default is dry-run")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    entities, parse_issues = load_entities(root)
    preflight_issues: list[dict[str, Any]] = []
    known_verifier_ids: set[str] = set()
    registry_loaded = False
    verification_methods: set[str] = set()
    contract_loaded = False
    try:
        known_verifier_ids = set(load_verifier_registry(root).ids)
        registry_loaded = True
    except VerifierRegistryError as exc:
        preflight_issues.append(
            issue(
                "critical",
                "VERIFIER_REGISTRY_READ",
                "schemas/verifiers.json",
                str(exc),
            )
        )
    if registry_loaded:
        mapped_verifier_ids = {
            verifier_id for verifier_id, _, _ in LEGACY_VERIFICATION_MAP.values()
        }
        missing_verifiers = mapped_verifier_ids - known_verifier_ids
        if missing_verifiers:
            preflight_issues.append(
                issue(
                    "critical",
                    "VERIFICATION_VERIFIER_MAPPING_DRIFT",
                    "schemas/verifiers.json",
                    "legacy migration verifier IDs are absent from the registry: "
                    + ", ".join(sorted(missing_verifiers)),
                    "verifiers",
                )
            )
    try:
        contract = load_schema_contract(root)
        contract_loaded = True
        verification_methods = set(contract.verification_methods)
        for problem in contract.problems:
            preflight_issues.append(
                issue(
                    "critical",
                    problem.code,
                    "schemas",
                    problem.message,
                    problem.field,
                )
            )
        mapped_methods = {method for _, method, _ in LEGACY_VERIFICATION_MAP.values()}
        missing_methods = mapped_methods - set(contract.verification_methods)
        if missing_methods:
            preflight_issues.append(
                issue(
                    "critical",
                    "VERIFICATION_METHOD_MAPPING_DRIFT",
                    "schemas",
                    "legacy migration methods are absent from the schema vocabulary: "
                    + ", ".join(sorted(missing_methods)),
                    "verification.methods",
                )
            )
    except SchemaContractError as exc:
        preflight_issues.append(
            issue(
                "critical",
                "SCHEMA_CONTRACT_READ",
                "schemas",
                str(exc),
            )
        )
    files: list[dict[str, Any]] = []
    planned_writes: list[tuple[Any, dict[str, Any], dict[str, Any]]] = []
    for entity in entities:
        migrated, details = migrate_data(entity.data, known_verifier_ids)
        validation_problems = (
            validate_verification(
                migrated,
                known_verifier_ids,
                verification_methods,
            )
            if registry_loaded and contract_loaded
            else ()
        )
        details["validation_problems"] = [
            {
                "severity": problem.severity,
                "code": problem.code,
                "field": problem.field,
                "message": problem.message,
            }
            for problem in validation_problems
        ]
        details.update({"path": entity.relative_path, "id": scalar_text(entity.data.get("id"))})
        files.append(details)
        if details["changed"]:
            planned_writes.append((entity, migrated, details))
    has_manual_review = any(
        item["unknown_legacy_values"]
        or item["existing_metadata_conflict"]
        or item["validation_problems"]
        for item in files
    )
    write_blocked = bool(args.write and (parse_issues or preflight_issues or has_manual_review))
    files_changed = 0
    write_error = ""
    if args.write and not write_blocked:
        try:
            files_changed = _apply_writes_atomically(planned_writes)
        except MigrationWriteError as exc:
            write_error = str(exc)
            write_blocked = True
    report = {
        "mode": "write" if args.write else "dry-run",
        "root": root.as_posix(),
        "summary": {
            "entities": len(entities),
            "files_changed": files_changed,
            "files_would_change": sum(bool(item["changed"]) for item in files),
            "write_blocked": write_blocked,
            "mapped": sum(bool(item["legacy_values"]) and not item["unknown_legacy_values"] for item in files),
            "empty_legacy_value": sum(not bool(item["legacy_values"]) for item in files),
            "unknown_legacy_value": sum(bool(item["unknown_legacy_values"]) for item in files),
            "existing_metadata_conflict": sum(bool(item["existing_metadata_conflict"]) for item in files),
            "verification_validation_problem": sum(bool(item["validation_problems"]) for item in files),
            "verifier_without_last_verified": sum(bool(item["verifier_without_last_verified"]) for item in files),
            "last_verified_without_verifier": sum(bool(item["last_verified_without_verifier"]) for item in files),
            "parse_issues": len(parse_issues),
            "preflight_issues": len(preflight_issues),
            "write_error": bool(write_error),
        },
        "parse_issues": parse_issues,
        "preflight_issues": preflight_issues,
        "write_error": write_error,
        "files": files,
    }
    write_json(report, args.output)
    return 1 if parse_issues or preflight_issues or has_manual_review or write_error else 0


if __name__ == "__main__":
    sys.exit(main())
