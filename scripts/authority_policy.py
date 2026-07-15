#!/usr/bin/env python3
"""Pure authority metadata diagnostics shared by repository linting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from kg_common import as_list, scalar_text


@dataclass(frozen=True)
class AuthorityDiagnostic:
    severity: str
    code: str
    message: str
    field: str = ""


def inferred_authority_levels(data: Mapping[str, Any], id_targets: Mapping[str, Any]) -> set[int]:
    """Infer conservative candidates; composite authorities may yield several levels."""

    levels: set[int] = set()
    text = scalar_text(data.get("primary_authority"))
    if any(word in text for word in ("헌법", "법률", "시행령", "시행규칙", "근로기준법", "최저임금법")):
        levels.add(1)
    if "전원합의체" in text:
        levels.add(2)
    elif "대법원" in text:
        levels.add(3)
    if any(word in text for word in ("고등법원", "지방법원", "지법", "고법")):
        levels.add(4)
    if any(word in text for word in ("고용노동부", "행정해석", "질의회시", "노사지도 지침")):
        levels.add(5)
    if any(word in text for word in ("단체협약", "취업규칙", "근로계약")):
        levels.add(6)
    primary_id = scalar_text(data.get("primary_authority_id"))
    target = id_targets.get(primary_id)
    if target and isinstance(target.data.get("authority_level"), int):
        levels.add(target.data["authority_level"])
    if data.get("entity_type") == "law":
        levels.add(1)
    elif data.get("entity_type") == "interpretation":
        levels.add(5)
    return levels


def authority_diagnostics(
    data: Mapping[str, Any],
    id_targets: Mapping[str, Any],
) -> tuple[AuthorityDiagnostic, ...]:
    diagnostics: list[AuthorityDiagnostic] = []
    ingestion = scalar_text(data.get("ingestion_status"))
    primary_id = data.get("primary_authority_id")
    authority_ids = data.get("authority_ids")
    level = data.get("authority_level")

    if primary_id is not None and not isinstance(primary_id, str):
        diagnostics.append(AuthorityDiagnostic("high", "PRIMARY_AUTHORITY_ID_TYPE", "primary_authority_id must be a string", "primary_authority_id"))
    if ingestion == "verified" and not scalar_text(primary_id):
        diagnostics.append(AuthorityDiagnostic("high", "PRIMARY_AUTHORITY_REQUIRED", "verified ingestion requires primary_authority_id", "primary_authority_id"))
    if ingestion == "verified" and not [scalar_text(value) for value in as_list(authority_ids) if scalar_text(value)]:
        diagnostics.append(AuthorityDiagnostic("high", "AUTHORITY_IDS_REQUIRED", "verified ingestion requires authority_ids", "authority_ids"))
    if not isinstance(level, int) or isinstance(level, bool):
        diagnostics.append(AuthorityDiagnostic("high", "AUTHORITY_LEVEL_TYPE", "authority_level must be an integer", "authority_level"))
    elif not 1 <= level <= 7:
        diagnostics.append(AuthorityDiagnostic("high", "AUTHORITY_LEVEL_RANGE", "authority_level must be between 1 and 7", "authority_level"))
    else:
        expected = inferred_authority_levels(data, id_targets)
        if expected and level not in expected:
            diagnostics.append(
                AuthorityDiagnostic(
                    "high",
                    "AUTHORITY_MISMATCH",
                    f"authority_level {level} conflicts with inferred levels {sorted(expected)}",
                    "authority_level",
                )
            )
    return tuple(diagnostics)
