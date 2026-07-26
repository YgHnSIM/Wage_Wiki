#!/usr/bin/env python3
"""Enforce the v1.4 no-growth quality budgets."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from claim_contract import evidence_claim_ids, resolved_claim_ids
from kg_common import load_entities, load_json, scalar_text, write_json


def _digest(pairs: set[tuple[str, str]]) -> str:
    rendered = "\n".join(f"{left}\t{right}" for left, right in sorted(pairs))
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def collect(root: Path) -> tuple[set[tuple[str, str]], set[tuple[str, str]], list[dict[str, Any]]]:
    entities, parse_issues = load_entities(root)
    claims: set[tuple[str, str]] = set()
    relations: set[tuple[str, str]] = set()
    for entity in entities:
        entity_id = scalar_text(entity.data.get("id"))
        provenance = entity.data.get("provenance") if isinstance(entity.data.get("provenance"), dict) else {}
        evidence = provenance.get("evidence", []) if isinstance(provenance, dict) else entity.data.get("evidence", [])
        resolved = resolved_claim_ids(entity.data, entity.body)
        for claim_id in evidence_claim_ids(evidence):
            if claim_id not in resolved:
                claims.add((entity_id, claim_id))
        for relation in entity.data.get("relations", []):
            if isinstance(relation, dict) and relation.get("relation_type") == "related_to":
                target_id = scalar_text(relation.get("target_id"))
                if entity_id and target_id:
                    relations.add((entity_id, target_id))
    return claims, relations, parse_issues


def check(root: Path, baseline_path: Path) -> dict[str, Any]:
    baseline = load_json(baseline_path, {})
    claims, relations, parse_issues = collect(root)
    issues: list[dict[str, Any]] = list(parse_issues)
    for name, current, key in (("claim_unresolved", claims, "claim_unresolved"), ("generic_relations", relations, "generic_relations")):
        expected = baseline.get(key, {}) if isinstance(baseline, dict) else {}
        count = int(expected.get("count", 0)) if isinstance(expected, dict) else 0
        digest = scalar_text(expected.get("sha256")) if isinstance(expected, dict) else ""
        if len(current) > count:
            issues.append({"severity": "high", "code": "QUALITY_BASELINE_GROWTH", "path": str(baseline_path), "field": key, "message": f"{key} grew from {count} to {len(current)}"})
        elif len(current) == count and digest and _digest(current) != digest:
            issues.append({"severity": "high", "code": "QUALITY_BASELINE_DRIFT", "path": str(baseline_path), "field": key, "message": f"{key} changed without shrinking"})
    return {"summary": {"claim_unresolved": len(claims), "generic_relations": len(relations), "issues": len(issues)}, "issues": issues}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--baseline", type=Path, default=Path("schemas/quality-baseline-v1.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    baseline = args.baseline if args.baseline.is_absolute() else root / args.baseline
    report = check(root, baseline)
    write_json(report, args.output)
    return 1 if report["issues"] else 0


if __name__ == "__main__":
    sys.exit(main())
