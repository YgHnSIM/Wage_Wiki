#!/usr/bin/env python3
"""Structured verifier identity and verification-method contract."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from kg_common import as_list, scalar_text


VERIFIER_REGISTRY_SCHEMA_VERSION = "1.0"
VERIFIER_ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
VERIFICATION_FIELDS = frozenset({"verifier_ids", "methods", "note"})
LEGACY_VERIFICATION_MAP: Mapping[str, tuple[str, str, str]] = MappingProxyType(
    {
        "codex-official-source-review": ("codex", "official_source_review", ""),
        "Codex 고용노동부 고시 원문 대조": ("codex", "source_cross_check", "고용노동부 고시 원문"),
        "Codex 공식 검색결과·보조 문헌 대조": ("codex", "source_cross_check", "공식 검색결과·보조 문헌"),
        "Codex 공식 원문 대조": ("codex", "source_cross_check", "공식 원문"),
        "Codex 공식 원문·연구문헌 대조": ("codex", "source_cross_check", "공식 원문·연구문헌"),
        "Codex 공식 원문·판례평석 대조": ("codex", "source_cross_check", "공식 원문·판례평석"),
        "Codex 공식 판결문 대조": ("codex", "source_cross_check", "공식 판결문"),
        "Codex 공식 판결문·고시 대조": ("codex", "source_cross_check", "공식 판결문·고시"),
        "Codex 판결 전문 대조": ("codex", "source_cross_check", "판결 전문"),
        "Codex 판결 전문·대법원 보도자료 대조": ("codex", "source_cross_check", "판결 전문·대법원 보도자료"),
    }
)


class VerifierRegistryError(ValueError):
    """Raised when the verifier registry cannot be loaded safely."""


@dataclass(frozen=True)
class VerifierRegistry:
    schema_version: str
    verifiers: Mapping[str, Mapping[str, Any]]

    @property
    def ids(self) -> frozenset[str]:
        return frozenset(self.verifiers)


@dataclass(frozen=True)
class VerificationProblem:
    severity: str
    code: str
    message: str
    field: str = "verification"


def load_verifier_registry(root: Path) -> VerifierRegistry:
    path = root / "schemas" / "verifiers.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VerifierRegistryError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("verifiers"), dict):
        raise VerifierRegistryError(f"{path} must contain a verifiers object")
    schema_version = value.get("schema_version")
    if schema_version != VERIFIER_REGISTRY_SCHEMA_VERSION:
        raise VerifierRegistryError(
            f"{path} schema_version must be {VERIFIER_REGISTRY_SCHEMA_VERSION}"
        )
    if not value["verifiers"]:
        raise VerifierRegistryError(f"{path} must contain at least one verifier")
    records: dict[str, Mapping[str, Any]] = {}
    for verifier_id, record in value["verifiers"].items():
        if not isinstance(verifier_id, str) or not VERIFIER_ID_RE.fullmatch(verifier_id):
            raise VerifierRegistryError(f"{path} contains an invalid verifier ID: {verifier_id!r}")
        if not isinstance(record, dict):
            raise VerifierRegistryError(f"{path} verifier {verifier_id} must be an object")
        for field in ("display_name", "kind"):
            field_value = record.get(field)
            if (
                not isinstance(field_value, str)
                or not field_value
                or field_value != field_value.strip()
            ):
                raise VerifierRegistryError(
                    f"{path} verifier {verifier_id}.{field} must be a nonempty trimmed string"
                )
        if "description" in record and not isinstance(record["description"], str):
            raise VerifierRegistryError(
                f"{path} verifier {verifier_id}.description must be a string"
            )
        records[verifier_id] = MappingProxyType(dict(record))
    return VerifierRegistry(
        schema_version=schema_version,
        verifiers=MappingProxyType(records),
    )


def normalize_legacy_verification(
    verified_by: Any,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Build additive structured metadata without rewriting the legacy field."""

    verifier_ids: list[str] = []
    methods: list[str] = []
    notes: list[str] = []
    unknown: list[str] = []

    for raw in as_list(verified_by):
        value = scalar_text(raw)
        if not value:
            continue
        mapping = LEGACY_VERIFICATION_MAP.get(raw) if isinstance(raw, str) else None
        if mapping:
            verifier_id, method, note = mapping
            verifier_ids.append(verifier_id)
            methods.append(method)
            if note:
                notes.append(note)
            continue
        unknown.append(raw if isinstance(raw, str) else value)

    return (
        {
            "verifier_ids": list(dict.fromkeys(verifier_ids)),
            "methods": list(dict.fromkeys(methods)),
            "note": " / ".join(dict.fromkeys(notes)),
        },
        tuple(dict.fromkeys(unknown)),
    )


def validate_verification(
    data: dict[str, Any],
    verifier_ids: set[str] | frozenset[str] | None,
    allowed_methods: set[str] | frozenset[str] | None,
) -> tuple[VerificationProblem, ...]:
    value = data.get("verification")
    legacy_values = [
        scalar_text(item)
        for item in as_list(data.get("verified_by"))
        if scalar_text(item)
    ]
    expected, unmapped_legacy = normalize_legacy_verification(data.get("verified_by"))
    direct_legacy_ids = (
        tuple(value for value in unmapped_legacy if value in verifier_ids)
        if verifier_ids is not None
        else ()
    )
    unknown_legacy = (
        tuple(value for value in unmapped_legacy if value not in verifier_ids)
        if verifier_ids is not None
        else ()
    )
    problems: list[VerificationProblem] = []
    if unknown_legacy:
        problems.append(
            VerificationProblem(
                "high",
                "VERIFICATION_LEGACY_UNKNOWN",
                "verified_by contains values without an exact migration mapping: "
                + ", ".join(unknown_legacy),
                "verified_by",
            )
        )
    if "verification" not in data:
        if legacy_values and not unknown_legacy:
            problems.append(
                VerificationProblem(
                    "high",
                    "VERIFICATION_LEGACY_MISSING",
                    "verified_by requires matching structured verification metadata",
                    "verification",
                )
            )
        return tuple(problems)
    if not isinstance(value, dict):
        problems.append(
            VerificationProblem("high", "VERIFICATION_TYPE", "verification must be a mapping")
        )
        return tuple(problems)

    parity_available = verifier_ids is not None or not unmapped_legacy
    if legacy_values and not unknown_legacy and parity_available and not legacy_verification_matches(
        value,
        expected,
        direct_legacy_ids,
    ):
        problems.append(
            VerificationProblem(
                "high",
                "VERIFICATION_LEGACY_DRIFT",
                "verification metadata differs from the exact verified_by mapping",
            )
        )
    for field in sorted(set(value) - VERIFICATION_FIELDS):
        problems.append(
            VerificationProblem(
                "high",
                "VERIFICATION_FIELD_UNKNOWN",
                f"verification contains an unsupported field: {field}",
            )
        )
    raw_ids = value.get("verifier_ids")
    raw_methods = value.get("methods")
    note = value.get("note")
    ids = [scalar_text(item) for item in raw_ids] if isinstance(raw_ids, list) else []
    methods = [scalar_text(item) for item in raw_methods] if isinstance(raw_methods, list) else []
    string_ids = [item for item in raw_ids if isinstance(item, str)] if isinstance(raw_ids, list) else []
    string_methods = [item for item in raw_methods if isinstance(item, str)] if isinstance(raw_methods, list) else []

    if not isinstance(raw_ids, list) or any(not isinstance(item, str) for item in raw_ids):
        problems.append(VerificationProblem("high", "VERIFIER_IDS_TYPE", "verification.verifier_ids must be a list of strings"))
    elif len(string_ids) != len(set(string_ids)):
        problems.append(VerificationProblem("medium", "VERIFIER_ID_DUPLICATE", "verification.verifier_ids contains duplicates"))
    if not isinstance(raw_methods, list) or any(not isinstance(item, str) for item in raw_methods):
        problems.append(VerificationProblem("high", "VERIFICATION_METHODS_TYPE", "verification.methods must be a list of strings"))
    elif len(string_methods) != len(set(string_methods)):
        problems.append(VerificationProblem("medium", "VERIFICATION_METHOD_DUPLICATE", "verification.methods contains duplicates"))
    if not isinstance(note, str):
        problems.append(VerificationProblem("high", "VERIFICATION_NOTE_TYPE", "verification.note must be a string"))

    if isinstance(raw_ids, list):
        for raw_id in raw_ids:
            if not isinstance(raw_id, str):
                continue
            if not VERIFIER_ID_RE.fullmatch(raw_id):
                problems.append(VerificationProblem("high", "VERIFIER_ID_INVALID", f"invalid verifier ID: {raw_id or '<empty>'}"))
            elif verifier_ids is not None and raw_id not in verifier_ids:
                problems.append(VerificationProblem("high", "VERIFIER_UNKNOWN", f"unknown verifier ID: {raw_id}"))
    if isinstance(raw_methods, list):
        for raw_method in raw_methods:
            if not isinstance(raw_method, str):
                continue
            if allowed_methods is not None and raw_method not in allowed_methods:
                problems.append(VerificationProblem("high", "VERIFICATION_METHOD_INVALID", f"invalid verification method: {raw_method or '<empty>'}"))

    has_ids = any(ids)
    has_methods = any(methods)
    has_note = bool(scalar_text(note))
    if has_ids and not has_methods:
        problems.append(VerificationProblem("high", "VERIFICATION_METHOD_MISSING", "verifier identity requires at least one verification method"))
    if (has_methods or has_note) and not has_ids:
        problems.append(VerificationProblem("high", "VERIFICATION_VERIFIER_MISSING", "verification method or note requires a verifier ID"))
    if "source_cross_check" in string_methods and not has_note:
        problems.append(VerificationProblem("high", "VERIFICATION_NOTE_MISSING", "source_cross_check requires a nonempty verification.note"))
    return tuple(problems)


def verification_matches(value: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    """Compare semantically unordered identity/method lists and an exact note."""

    raw_ids = value.get("verifier_ids")
    raw_methods = value.get("methods")
    if not isinstance(raw_ids, list) or not isinstance(raw_methods, list):
        return False
    if any(not isinstance(item, str) for item in raw_ids + raw_methods):
        return False
    return (
        set(raw_ids) == set(expected["verifier_ids"])
        and set(raw_methods) == set(expected["methods"])
        and value.get("note") == expected["note"]
    )


def legacy_verification_matches(
    value: Mapping[str, Any],
    mapped: Mapping[str, Any],
    direct_ids: tuple[str, ...],
) -> bool:
    """Keep mapped prose exact while allowing registry IDs to choose their method."""

    if not direct_ids:
        return verification_matches(value, mapped)
    raw_ids = value.get("verifier_ids")
    raw_methods = value.get("methods")
    if not isinstance(raw_ids, list) or not isinstance(raw_methods, list):
        return False
    if any(not isinstance(item, str) for item in raw_ids + raw_methods):
        return False
    expected_ids = set(mapped["verifier_ids"]) | set(direct_ids)
    return (
        set(raw_ids) == expected_ids
        and set(mapped["methods"]).issubset(raw_methods)
        and (not mapped["note"] or value.get("note") == mapped["note"])
    )


def has_verifier_identity(data: Mapping[str, Any]) -> bool:
    """Return true only for a nonblank legacy or structured verifier identity."""

    if any(scalar_text(value) for value in as_list(data.get("verified_by"))):
        return True
    verification = data.get("verification")
    return isinstance(verification, dict) and any(
        isinstance(value, str) and bool(value.strip())
        for value in as_list(verification.get("verifier_ids"))
    )
