#!/usr/bin/env python3
"""Pure cross-field diagnostics for supersession time metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from kg_common import parse_date, scalar_text


OPEN_ENDED_DATE = "9999-12-31"
TERMINATED_LEGAL_STATUSES = frozenset({"superseded", "overruled"})


@dataclass(frozen=True)
class TemporalDiagnostic:
    severity: str
    code: str
    message: str
    field: str = ""


def supersession_diagnostics(
    data: Mapping[str, Any],
    id_targets: Mapping[str, Any],
) -> tuple[TemporalDiagnostic, ...]:
    """Diagnose contradictions without guessing the legally correct end date."""

    diagnostics: list[TemporalDiagnostic] = []
    entity_id = scalar_text(data.get("id"))
    target_id = scalar_text(data.get("superseded_by"))
    superseded_date = parse_date(data.get("superseded_date"))
    effective_from = parse_date(data.get("effective_from"))
    legal_status = scalar_text(data.get("legal_status"))

    if target_id:
        target = id_targets.get(target_id)
        target_data = getattr(target, "data", target if isinstance(target, Mapping) else {})
        canonical_target_id = (
            scalar_text(target_data.get("id")) if isinstance(target_data, Mapping) else ""
        )
        if target_id == entity_id or canonical_target_id == entity_id:
            diagnostics.append(
                TemporalDiagnostic(
                    "critical",
                    "SUPERSESSION_SELF_REFERENCE",
                    "superseded_by cannot refer to the same entity",
                    "superseded_by",
                )
            )
        elif target is None:
            diagnostics.append(
                TemporalDiagnostic(
                    "critical",
                    "SUPERSESSION_TARGET_BROKEN",
                    f"unknown supersession target: {target_id}",
                    "superseded_by",
                )
            )
    if superseded_date and effective_from and superseded_date < effective_from:
        diagnostics.append(
            TemporalDiagnostic(
                "high",
                "SUPERSESSION_DATE_ORDER",
                "superseded_date is earlier than effective_from",
                "superseded_date",
            )
        )
    if legal_status in TERMINATED_LEGAL_STATUSES and scalar_text(data.get("effective_to")) == OPEN_ENDED_DATE:
        diagnostics.append(
            TemporalDiagnostic(
                "medium",
                "SUPERSESSION_OPEN_ENDED",
                "superseded/overruled metadata has an open-ended effective_to; legal review is required",
                "effective_to",
            )
        )
    return tuple(diagnostics)
