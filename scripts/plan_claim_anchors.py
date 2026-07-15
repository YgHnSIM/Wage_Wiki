#!/usr/bin/env python3
"""Inventory evidence claims and produce a manual body-anchor migration plan."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from claim_contract import (
    CLAIM_ID_RE,
    claim_anchors,
    evidence_claim_ids,
    fence_closes,
    fence_spec,
    global_claim_id,
    resolved_claim_ids,
)
from kg_common import as_list, load_entities, scalar_text, write_json


_HEADING_RE = re.compile(r"^(#{2,4})\s+(.+?)\s*$")


def _sections(body: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    fence: tuple[str, int] | None = None
    for line_number, line in enumerate(body.splitlines(), 1):
        if fence is not None:
            if fence_closes(line, *fence):
                fence = None
            continue
        opener = fence_spec(line)
        if opener is not None:
            fence = opener[:2]
            continue
        match = _HEADING_RE.match(line)
        if match:
            result.append({"line": line_number, "level": len(match.group(1)), "title": match.group(2)})
    return result


def plan_entity(entity: Any) -> dict[str, Any] | None:
    supported = evidence_claim_ids(entity.data.get("evidence"))
    if not supported:
        return None
    entity_id = scalar_text(entity.data.get("id"))
    anchors = claim_anchors(entity.body)
    resolved = resolved_claim_ids(entity.data, entity.body)
    anchors_by_id: dict[str, list[Any]] = {}
    for anchor in anchors:
        anchors_by_id.setdefault(anchor.claim_id, []).append(anchor)
    evidence_by_claim: dict[str, list[dict[str, str]]] = {claim_id: [] for claim_id in supported}
    for record in as_list(entity.data.get("evidence")):
        if not isinstance(record, dict):
            continue
        evidence_record = {
            "evidence_id": scalar_text(record.get("evidence_id")),
            "source_id": scalar_text(record.get("source_id")),
            "locator": scalar_text(record.get("locator")),
            "excerpt": scalar_text(record.get("excerpt")),
        }
        for raw in as_list(record.get("supports")):
            claim_id = scalar_text(raw)
            if claim_id in evidence_by_claim:
                evidence_by_claim[claim_id].append(evidence_record)
    claims = []
    for claim_id in supported:
        matches = anchors_by_id.get(claim_id, [])
        claims.append({
            "claim_id": claim_id,
            "global_claim_id": global_claim_id(entity_id, claim_id),
            "valid_id": bool(CLAIM_ID_RE.fullmatch(claim_id)),
            "resolved": claim_id in resolved,
            "anchors": [
                {"line": match.line, "text": match.text} for match in matches
            ],
            "evidence": evidence_by_claim[claim_id],
            "manual_review_required": claim_id not in resolved,
        })
    return {
        "path": entity.relative_path,
        "id": entity_id,
        "title": scalar_text(entity.data.get("title")),
        "sections": _sections(entity.body),
        "claims": claims,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, help="write JSON plan; stdout when omitted")
    parser.add_argument("--fail-on-unresolved", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    entities, parse_issues = load_entities(root)
    documents = [record for entity in entities if (record := plan_entity(entity)) is not None]
    claims = [claim for document in documents for claim in document["claims"]]
    report = {
        "root": root.as_posix(),
        "summary": {
            "entities": len(entities),
            "documents_with_claims": len(documents),
            "local_claims": len(claims),
            "resolved_claims": sum(bool(claim["resolved"]) for claim in claims),
            "unresolved_claims": sum(not bool(claim["resolved"]) for claim in claims),
            "invalid_claim_ids": sum(not bool(claim["valid_id"]) for claim in claims),
            "parse_issues": len(parse_issues),
        },
        "parse_issues": parse_issues,
        "documents": documents,
    }
    write_json(report, args.output)
    unresolved = report["summary"]["unresolved_claims"]
    return 1 if parse_issues or (args.fail_on_unresolved and unresolved) else 0


if __name__ == "__main__":
    sys.exit(main())
