#!/usr/bin/env python3
"""Pure workflow diagnostics for evidence and document verification dates."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Mapping

from kg_common import as_list, parse_date, scalar_text


@dataclass(frozen=True)
class VerificationDiagnostic:
    severity: str
    code: str
    message: str
    field: str = ""


def verification_timeline_diagnostics(
    data: Mapping[str, Any],
    today: dt.date,
    *,
    source_entity: bool,
) -> tuple[VerificationDiagnostic, ...]:
    """Keep evidence review, ingestion, and document verification as separate axes."""

    diagnostics: list[VerificationDiagnostic] = []
    status = scalar_text(data.get("status"))
    ingestion = scalar_text(data.get("ingestion_status"))
    last_verified = parse_date(data.get("last_verified"))
    last_checked = parse_date(data.get("last_checked"))
    evidence = [record for record in as_list(data.get("evidence")) if isinstance(record, dict)]

    for index, record in enumerate(evidence):
        verified_on = parse_date(record.get("verified_on"))
        if verified_on and verified_on > today:
            diagnostics.append(
                VerificationDiagnostic(
                    "high",
                    "EVIDENCE_VERIFIED_IN_FUTURE",
                    "evidence.verified_on is later than the lint date",
                    f"evidence[{index}].verified_on",
                )
            )
        if status == "verified" and verified_on and last_verified and verified_on > last_verified:
            diagnostics.append(
                VerificationDiagnostic(
                    "high",
                    "EVIDENCE_AFTER_LAST_VERIFIED",
                    "claim evidence was verified after the document's last_verified date",
                    f"evidence[{index}].verified_on",
                )
            )
    if status == "verified" and last_verified and last_checked and last_verified > last_checked:
        diagnostics.append(
            VerificationDiagnostic(
                "high",
                "VERIFICATION_AFTER_CHECK",
                "last_verified is later than last_checked",
                "last_checked",
            )
        )
    if status != "verified" and ingestion == "verified" and source_entity and not evidence:
        diagnostics.append(
            VerificationDiagnostic(
                "medium",
                "INGESTION_VERIFIED_EVIDENCE_MISSING",
                "verified ingestion for an authority entity has no claim-level evidence",
                "evidence",
            )
        )
    return tuple(diagnostics)
