#!/usr/bin/env python3
"""Migrate v1.3 entity frontmatter to the v1.4 normalized contract.

The command is dry-run by default.  ``--write`` performs one deterministic
batch after every entity has been transformed successfully.  Raw files are
never touched.  Legacy related_* links are folded into ``relations`` as
``related_to`` and then emitted again as generated Obsidian projections.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from kg_common import (
    CURRENT_SCHEMA_VERSION,
    Entity,
    as_list,
    dump_subset_yaml,
    entity_lookup,
    load_entities,
    load_json,
    provenance_data,
    scalar_text,
    wiki_targets,
    workflow_data,
    write_json,
)


ENTITY_TYPES = {"guide", "concept", "rule", "case", "law", "interpretation", "history", "discussion", "fact_pattern"}
AUTHORITY_TYPES = {"case", "law", "interpretation"}
RELATED_FIELD_TYPES = {
    "related_guides": "guide",
    "related_concepts": "concept",
    "related_rules": "rule",
    "related_cases": "case",
    "related_laws": "law",
    "related_interpretations": "interpretation",
    "related_history": "history",
    "related_discussions": "discussion",
    "related_fact_patterns": "fact_pattern",
}
LEGACY_RELATED_FIELDS = {
    "related_concepts": "concept",
    "related_rules": "rule",
    "related_cases": "case",
    "related_laws": "law",
    "related_interpretations": "interpretation",
    "related_fact_patterns": "fact_pattern",
    "related_raw": None,
}
RELATION_TYPES = {
    "establishes", "applies", "interprets", "distinguishes", "overrules", "supersedes",
    "exception_to", "illustrated_by", "supports", "cites", "amends", "implements", "related_to",
}
RELATION_MAP = {
    "conflicts_with": "related_to",
    "related": "related_to",
    "relates_to": "related_to",
}
EVIDENCE_ID_RE = re.compile(r"[^a-z0-9-]+")


def _date(value: Any, *, null_sentinel: bool = False) -> str | None:
    text = scalar_text(value)
    if not text:
        return None
    if null_sentinel and text in {"9999-12-31", "1900-01-01"}:
        return None
    return text


def _slug(value: str, prefix: str) -> str:
    value = EVIDENCE_ID_RE.sub("-", value.casefold()).strip("-") or "item"
    return f"{prefix}{value[:80]}"


def _target_id(reference: str, names: dict[str, list[Entity]]) -> str:
    reference = scalar_text(reference)
    if not reference:
        return ""
    from kg_common import resolve_entity_ref

    candidates = wiki_targets(reference) or [reference]
    matches = resolve_entity_ref(candidates[0], names)
    if len(matches) == 1:
        return scalar_text(matches[0].data.get("id"))
    return reference


def _display_link(entity_id: str, by_id: dict[str, Entity]) -> str:
    target = by_id.get(entity_id)
    title = scalar_text(target.data.get("title")) if target else entity_id
    return f"[[{title or entity_id}]]"


def _relation_type(value: Any) -> str:
    relation = scalar_text(value)
    relation = RELATION_MAP.get(relation, relation)
    return relation if relation in RELATION_TYPES else "related_to"


def _normalise_relations(entity: Entity, names: dict[str, list[Entity]], by_id: dict[str, Entity]) -> tuple[list[dict[str, Any]], list[str]]:
    data = entity.data
    records: list[dict[str, Any]] = []
    unresolved: list[str] = []

    def add(relation_type: str, target: str, note: str = "", effective_on: str | None = None) -> None:
        target_id = _target_id(target, names)
        if not target_id:
            return
        if target_id not in by_id:
            unresolved.append(target_id)
        record = {
            "relation_type": _relation_type(relation_type),
            "target_id": target_id,
            "note": scalar_text(note),
            "effective_on": _date(effective_on),
        }
        if record not in records:
            records.append(record)

    for raw in as_list(data.get("relations")):
        if isinstance(raw, dict):
            # v1.4 models conflict semantics as first-class records rather
            # than weakening them into a generic related_to edge.
            if scalar_text(raw.get("relation_type")) == "conflicts_with":
                continue
            add(raw.get("relation_type"), raw.get("target_id") or raw.get("target"), raw.get("note"), raw.get("effective_on"))
    for field in LEGACY_RELATED_FIELDS:
        if field == "related_raw":
            continue
        for target in as_list(data.get(field)):
            add("related_to", target)
    records.sort(key=lambda item: (item["relation_type"], item["target_id"], item["note"], item["effective_on"] or ""))
    return records, sorted(set(unresolved))


def _normalise_authorities(data: dict[str, Any], names: dict[str, list[Entity]], by_id: dict[str, Entity]) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    unresolved: list[str] = []
    primary = scalar_text(data.get("primary_authority_id"))
    candidates = [primary] + [scalar_text(item) for item in as_list(data.get("authority_ids"))]
    for candidate in dict.fromkeys(item for item in candidates if item):
        target_id = _target_id(candidate, names)
        target = by_id.get(target_id)
        if target is None:
            unresolved.append(target_id)
            continue
        if scalar_text(target.data.get("entity_type")) not in AUTHORITY_TYPES:
            # v1.3 occasionally treated rules as authorities; v1.4 keeps
            # authority edges restricted to case/law/interpretation.
            unresolved.append(target_id)
            continue
        role = "primary" if target_id == _target_id(primary, names) else "supporting"
        record = {"target_id": target_id, "role": role, "note": ""}
        if record not in records:
            records.append(record)
    records.sort(key=lambda item: (0 if item["role"] == "primary" else 1, item["target_id"]))
    return records, sorted(set(unresolved))


def _normalise_evidence(data: dict[str, Any], entity_id: str) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    source_ids: list[str] = []
    for raw in as_list(data.get("evidence")):
        if not isinstance(raw, dict):
            continue
        source_id = scalar_text(raw.get("source_id"))
        locator = scalar_text(raw.get("locator"))
        supports = [scalar_text(item) for item in as_list(raw.get("supports")) if scalar_text(item)]
        if not source_id or not locator or not supports:
            continue
        old_id = scalar_text(raw.get("evidence_id"))
        evidence_id = old_id if old_id.startswith("evidence:") else _slug(f"{entity_id}-{old_id}", "evidence:")
        digest = hashlib.sha256(f"{entity_id}\0{source_id}\0{locator}\0{old_id}".encode("utf-8")).hexdigest()[:10]
        if evidence_id.endswith(digest) is False and len(evidence_id) >= 90:
            evidence_id = evidence_id[:78].rstrip("-") + "-" + digest
        record = {
            "evidence_id": evidence_id,
            "source_id": source_id,
            "locator": locator,
            "excerpt": scalar_text(raw.get("excerpt")),
            "supports": list(dict.fromkeys(supports)),
            "verified_on": _date(raw.get("verified_on")),
        }
        if record not in records:
            records.append(record)
        if source_id not in source_ids:
            source_ids.append(source_id)
    return records, source_ids


def _repair_v14_data(data: dict[str, Any]) -> dict[str, Any]:
    """Make a previously migrated document idempotently unique and sorted."""

    repaired = dict(data)
    provenance = dict(repaired.get("provenance") or {})
    evidence = []
    seen_evidence: set[str] = set()
    for index, raw in enumerate(provenance.get("evidence", []) if isinstance(provenance.get("evidence"), list) else []):
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        evidence_id = scalar_text(item.get("evidence_id")) or _slug(f"{repaired.get('id', 'entity')}-{index}", "evidence:")
        if evidence_id in seen_evidence:
            digest = hashlib.sha256(f"{repaired.get('id')}\0{index}\0{item.get('source_id')}\0{item.get('locator')}".encode("utf-8")).hexdigest()[:10]
            evidence_id = evidence_id[:78].rstrip("-") + "-" + digest
        item["evidence_id"] = evidence_id
        seen_evidence.add(evidence_id)
        evidence.append(item)
    provenance["evidence"] = evidence
    repaired["provenance"] = provenance
    relations = []
    seen_relations: set[tuple[Any, ...]] = set()
    for raw in repaired.get("relations", []) if isinstance(repaired.get("relations"), list) else []:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        key = (item.get("relation_type"), item.get("target_id"), item.get("note", ""), item.get("effective_on"))
        if key not in seen_relations:
            relations.append(item)
            seen_relations.add(key)
    repaired["relations"] = sorted(relations, key=lambda item: (scalar_text(item.get("relation_type")), scalar_text(item.get("target_id")), scalar_text(item.get("note"))))
    return repaired


def _normalise_conflicts(
    data: dict[str, Any],
    relations: list[dict[str, Any]],
    entity_id: str,
    names: dict[str, list[Entity]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    conflicts: list[dict[str, Any]] = []
    retained: list[dict[str, Any]] = []
    for raw in as_list(data.get("conflicts")):
        if isinstance(raw, dict):
            conflicts.append({
                "conflict_id": scalar_text(raw.get("conflict_id")) or _slug(f"{entity_id}-conflict", "conflict:"),
                "type": scalar_text(raw.get("type")) or "interpretive",
                "status": scalar_text(raw.get("status")) or "pending",
                "target_ids": [scalar_text(item) for item in as_list(raw.get("target_ids")) if scalar_text(item)],
                "note": scalar_text(raw.get("note")),
                "resolved_on": _date(raw.get("resolved_on")),
                "review_triggers": [scalar_text(item) for item in as_list(raw.get("review_triggers")) if scalar_text(item)],
            })
    legacy_status = scalar_text(data.get("conflict_status"))
    legacy_resolution = scalar_text(data.get("conflict_resolution"))
    legacy_type = scalar_text(data.get("conflict_type"))
    if not conflicts and (legacy_status == "active" or legacy_resolution in {"pending", "resolved", "unresolvable"}):
        conflicts.append({
            "conflict_id": _slug(f"{entity_id}-legacy", "conflict:"),
            "type": legacy_type if legacy_type in {"authority", "temporal", "interpretive", "jurisdictional"} else "interpretive",
            "status": legacy_resolution if legacy_resolution in {"pending", "resolved", "unresolvable"} else "pending",
            "target_ids": [],
            "note": scalar_text(data.get("conflict_resolution_note")),
            "resolved_on": _date(data.get("conflict_resolved_date")),
            "review_triggers": [scalar_text(item) for item in as_list(data.get("review_trigger")) if scalar_text(item)],
        })
    # Preserve every legacy conflicts_with relation as an independently
    # addressable conflict record, including its target and explanatory note.
    legacy_status_value = legacy_resolution if legacy_resolution in {"pending", "resolved", "unresolvable"} else "pending"
    conflict_type_value = legacy_type if legacy_type in {"authority", "temporal", "interpretive", "jurisdictional"} else "interpretive"
    existing_targets = {
        target
        for conflict in conflicts
        for target in as_list(conflict.get("target_ids"))
        if scalar_text(target)
    }
    for raw in as_list(data.get("relations")):
        if not isinstance(raw, dict) or scalar_text(raw.get("relation_type")) != "conflicts_with":
            continue
        target = _target_id(raw.get("target_id") or raw.get("target"), names)
        if not target or target in existing_targets:
            continue
        conflicts.append({
            "conflict_id": _slug(f"{entity_id}-{target}", "conflict:"),
            "type": conflict_type_value,
            "status": legacy_status_value,
            "target_ids": [target],
            "note": scalar_text(raw.get("note")),
            "resolved_on": _date(data.get("conflict_resolved_date")) if legacy_status_value == "resolved" else None,
            "review_triggers": [scalar_text(item) for item in as_list(data.get("review_trigger")) if scalar_text(item)],
        })
        existing_targets.add(target)
    retained.extend(relations)
    conflicts.sort(key=lambda item: scalar_text(item.get("conflict_id")))
    return conflicts, retained


def _attributes(data: dict[str, Any], entity_type: str) -> dict[str, Any]:
    if entity_type == "case":
        raw_numbers = data.get("case_numbers")
        numbers: list[dict[str, str]] = []
        if isinstance(raw_numbers, list):
            for index, value in enumerate(raw_numbers):
                if isinstance(value, dict):
                    number = scalar_text(value.get("number"))
                    role = scalar_text(value.get("role")) or ("primary" if index == 0 else "joined")
                else:
                    number, role = scalar_text(value), ("primary" if index == 0 else "joined")
                if number:
                    numbers.append({"number": number, "role": role if role in {"primary", "joined", "principal_action", "counterclaim"} else "joined"})
        if not numbers and scalar_text(data.get("case_number")):
            numbers = [{"number": scalar_text(data.get("case_number")), "role": "primary"}]
        return {
            "court_name": scalar_text(data.get("court_name")) or "미상",
            "case_numbers": numbers or [{"number": "미상", "role": "primary"}],
            "decision_date": _date(data.get("decision_date")) or _date(data.get("effective_from")) or "1900-01-01",
            "case_role": scalar_text(data.get("case_role")) or "persuasive",
            "holding_summary": scalar_text(data.get("holding_summary")) or "검토 필요",
            "legal_principles": [scalar_text(item) for item in as_list(data.get("legal_principles")) if scalar_text(item)] or ["검토 필요"],
        }
    if entity_type == "rule":
        temporal = data.get("temporal") if isinstance(data.get("temporal"), dict) else {}
        return {
            "rule_type": scalar_text(data.get("rule_type")) or "procedure",
            "issue": scalar_text(data.get("issue")) or "검토 필요",
            "elements": [scalar_text(item) for item in as_list(data.get("elements")) if scalar_text(item)] or ["검토 필요"],
            "exceptions": [scalar_text(item) for item in as_list(data.get("exceptions")) if scalar_text(item)],
            "conclusion": scalar_text(data.get("conclusion")) or "검토 필요",
            "rule_version": scalar_text(data.get("rule_version")) or scalar_text(temporal.get("rule_version")) or "legacy",
            "transition_note": scalar_text(data.get("transition_note")) or scalar_text(temporal.get("transition_note")),
            "law_version": scalar_text(data.get("law_version")) or None,
            "law_revision_date": _date(data.get("law_revision_date")),
            "wage_criteria": [scalar_text(item) for item in as_list(data.get("wage_criteria")) if scalar_text(item)],
            "decision_factors": [scalar_text(item) for item in as_list(data.get("decision_factors")) if scalar_text(item)],
            "wage_type": [scalar_text(item) for item in as_list(data.get("wage_type")) if scalar_text(item)],
            "worker_scope": scalar_text(data.get("worker_scope")),
            "calculation_unit": scalar_text(data.get("calculation_unit")),
            "extinction_period": scalar_text(data.get("extinction_period")) or "해당 없음",
        }
    if entity_type == "law":
        return {
            "law_version": scalar_text(data.get("law_version")) or "검토 필요",
            "law_revision_date": _date(data.get("law_revision_date")) or _date(data.get("effective_from")) or "1900-01-01",
            "promulgation_date": _date(data.get("promulgation_date")) or _date(data.get("effective_from")) or "1900-01-01",
            "enforcement_date": _date(data.get("enforcement_date")) or _date(data.get("effective_from")) or "1900-01-01",
        }
    if entity_type == "interpretation":
        return {
            "issuing_agency": scalar_text(data.get("issuing_agency")) or "검토 필요",
            "document_number": scalar_text(data.get("document_number")) or "검토 필요",
            "issue_date": _date(data.get("issue_date")) or _date(data.get("effective_from")) or "1900-01-01",
            "interpretation_type": scalar_text(data.get("interpretation_type")) or "official_reply",
            "legal_effect": scalar_text(data.get("legal_effect")) or "persuasive",
        }
    return {}


def migrate_entity(entity: Entity, names: dict[str, list[Entity]], by_id: dict[str, Entity], verifier_ids: set[str], as_of: dt.date) -> tuple[dict[str, Any], dict[str, Any]]:
    old = entity.data
    entity_id = scalar_text(old.get("id"))
    entity_type = scalar_text(old.get("entity_type"))
    if scalar_text(old.get("schema_version")) == CURRENT_SCHEMA_VERSION:
        repaired = _repair_v14_data(old)
        return repaired, {
            "path": entity.relative_path,
            "id": entity_id,
            "downgraded_verified": False,
            "source_excerpt_review": False,
            "unresolved_relations": [],
            "unresolved_authorities": [],
            "evidence_count": len(as_list((old.get("provenance") or {}).get("evidence"))) if isinstance(old.get("provenance"), dict) else 0,
            "would_change": repaired != old,
        }
    relations, unresolved_relations = _normalise_relations(entity, names, by_id)
    conflicts, relations = _normalise_conflicts(old, relations, entity_id, names)
    authorities, unresolved_authorities = _normalise_authorities(old, names, by_id)
    evidence, evidence_sources = _normalise_evidence(old, entity_id)
    provenance = provenance_data(old)
    source_excerpt = [scalar_text(item) for item in as_list(old.get("source_excerpt")) if scalar_text(item)]
    external_links = []
    for item in provenance.get("external_links", []):
        url = scalar_text(item.get("url"))
        if not url:
            continue
        role = scalar_text(item.get("role")) or ("official" if any(domain in url.casefold() for domain in ("law.go.kr", "scourt.go.kr", "moel.go.kr")) else "reference")
        external_links.append({"url": url, "role": role if role in {"official", "official_search", "reference"} else "reference", "note": scalar_text(item.get("note"))})
    verification_old = provenance.get("verification") if isinstance(provenance.get("verification"), dict) else {}
    legacy_verifiers = [scalar_text(item) for item in as_list(old.get("verified_by")) if scalar_text(item)]
    structured_verifiers = [scalar_text(item) for item in as_list(verification_old.get("verifier_ids")) if scalar_text(item) and scalar_text(item) in verifier_ids]
    verifier_note = scalar_text(verification_old.get("note"))
    unknown_verifiers = [item for item in legacy_verifiers if item not in verifier_ids]
    if unknown_verifiers:
        verifier_note = "; ".join(item for item in [verifier_note, f"legacy verified_by: {', '.join(unknown_verifiers)}"] if item)
    verified_on = _date(verification_old.get("verified_on")) or _date(old.get("last_verified"))
    methods = [scalar_text(item) for item in as_list(verification_old.get("methods")) if scalar_text(item) in {"official_source_review", "source_cross_check"}]
    if not methods and verified_on and external_links:
        methods = ["official_source_review"] if any(item["role"] in {"official", "official_search"} for item in external_links) else ["source_cross_check"]
    verification = {"verified_on": verified_on, "verifier_ids": list(dict.fromkeys(structured_verifiers)), "methods": list(dict.fromkeys(methods)), "note": verifier_note}
    old_workflow = workflow_data(old)
    editorial_status = old_workflow["editorial_status"] if old_workflow["editorial_status"] in {"draft", "review", "verified"} else "review"
    ingestion_status = old_workflow["ingestion_status"] if old_workflow["ingestion_status"] in {"imported", "extracted", "linked", "verified"} else "linked"
    complete_verification = bool(verified_on and structured_verifiers and methods)
    if source_excerpt and not evidence:
        # A legacy excerpt is an editorial lead, not claim-level provenance.
        # Keep it visible in provenance.note but require a human review before
        # the entity can remain verified.
        editorial_status, ingestion_status = "review", "linked"
    elif editorial_status == "verified" or ingestion_status == "verified":
        if not complete_verification or (entity_type in AUTHORITY_TYPES and not evidence):
            editorial_status, ingestion_status = "review", "linked"
    updated_on = _date(old_workflow["updated_on"]) or as_of.isoformat()
    review = old_workflow.get("review") or {}
    cycle = scalar_text(review.get("cycle")) or "annual"
    if cycle not in {"monthly", "quarterly", "annual"}:
        cycle = "annual"
    checked_on = _date(review.get("checked_on")) or _date(old.get("last_checked"))
    triggers = [scalar_text(item) for item in as_list(review.get("triggers")) if scalar_text(item)]
    legal_status = scalar_text(old.get("legal_status")) or "unknown"
    superseded_by = _target_id(scalar_text(old.get("superseded_by")), names) or None
    superseded_on = _date(old.get("superseded_date"))
    validity_until = _date(old.get("effective_to"), null_sentinel=True)
    if source_excerpt and not evidence:
        note = "; ".join(item for item in [scalar_text(provenance.get("note")), "legacy source_excerpt: " + " | ".join(source_excerpt)] if item)
    else:
        note = scalar_text(provenance.get("note"))
    availability = provenance.get("availability")
    if availability not in {"complete", "partial", "official_unavailable", "not_applicable"}:
        availability = "not_applicable"
    if entity_type in AUTHORITY_TYPES and not evidence and availability == "complete":
        availability = "partial"
    authority_profile = None
    if entity_type in AUTHORITY_TYPES:
        level = old.get("authority_level")
        weight = scalar_text(old.get("enforcement_weight"))
        authority_profile = {"level": level if isinstance(level, int) and not isinstance(level, bool) else 7, "enforcement_weight": weight if weight in {"critical", "high", "medium", "low"} else "low"}
    result: dict[str, Any] = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "id": entity_id,
        "id_aliases": [scalar_text(item) for item in as_list(old.get("id_aliases")) if scalar_text(item)],
        "entity_type": entity_type,
        "title": scalar_text(old.get("title")) or entity.path.stem,
        "aliases": [scalar_text(item) for item in as_list(old.get("aliases")) if scalar_text(item)],
        "jurisdiction": scalar_text(old.get("jurisdiction")) or "KR",
        "workflow": {"editorial_status": editorial_status, "ingestion_status": ingestion_status, "updated_on": updated_on, "review": {"cycle": cycle, "checked_on": checked_on, "triggers": list(dict.fromkeys(triggers))}},
        "legal": {"status": legal_status, "as_of": _date(old.get("as_of_date")) or as_of.isoformat(), "validity": {"from": _date(old.get("effective_from")) or "1900-01-01", "until": validity_until}, "superseded_by": superseded_by, "superseded_on": superseded_on},
        "authority_profile": authority_profile,
        "authorities": authorities,
        "provenance": {"availability": availability, "note": note, "source_ids": list(dict.fromkeys(evidence_sources + [scalar_text(item) for item in provenance.get("source_ids", []) if scalar_text(item)])), "external_links": external_links, "evidence": evidence, "verification": verification},
        "conflicts": conflicts,
        "relations": relations,
        "attributes": _attributes(old, entity_type),
    }
    for field, expected_type in RELATED_FIELD_TYPES.items():
        targets: list[str] = []
        for relation in relations:
            target = by_id.get(relation["target_id"])
            if target is not None and scalar_text(target.data.get("entity_type")) == expected_type and relation["target_id"] not in targets:
                targets.append(relation["target_id"])
        result[field] = [_display_link(target, by_id) for target in sorted(targets)]
    result["related_raw"] = [scalar_text(item) for item in as_list(old.get("related_raw")) if scalar_text(item)]
    report = {
        "path": entity.relative_path,
        "id": entity_id,
        "downgraded_verified": (editorial_status, ingestion_status) != (old_workflow["editorial_status"], old_workflow["ingestion_status"]) and (old_workflow["editorial_status"] == "verified" or old_workflow["ingestion_status"] == "verified"),
        "source_excerpt_review": bool(source_excerpt and not evidence),
        "unresolved_relations": unresolved_relations,
        "unresolved_authorities": unresolved_authorities,
        "evidence_count": len(evidence),
        "would_change": False,
    }
    return result, report


def _render(data: dict[str, Any], body: str) -> str:
    return "---\n" + dump_subset_yaml(data) + "---\n" + body.lstrip("\r\n")


def migrate(root: Path, *, as_of: dt.date, write: bool = False, output: Path | None = None) -> dict[str, Any]:
    entities, parse_issues = load_entities(root)
    by_id, names = entity_lookup(entities)
    verifier_registry = load_json(root / "schemas" / "verifiers.json", {}).get("verifiers", {})
    verifier_ids = set(verifier_registry) if isinstance(verifier_registry, dict) else set()
    changes: list[dict[str, Any]] = []
    rendered: list[tuple[Entity, str]] = []
    for entity in entities:
        data, report = migrate_entity(entity, names, by_id, verifier_ids, as_of)
        content = _render(data, entity.body)
        original = entity.path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        report["would_change"] = original != content.replace("\r\n", "\n")
        changes.append(report)
        rendered.append((entity, content))
    if write and not parse_issues:
        # Stage every file first.  A failure while staging leaves the source
        # tree untouched; replacements happen only after all renders succeed.
        staged: list[tuple[Path, Path]] = []
        try:
            for entity, content in rendered:
                temp = entity.path.with_name(f".{entity.path.name}.v14.tmp")
                temp.write_text(content, encoding="utf-8", newline="\n")
                staged.append((temp, entity.path))
            for temp, target in staged:
                temp.replace(target)
        finally:
            for temp, _ in staged:
                if temp.exists():
                    temp.unlink()
    report = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "mode": "write" if write else "dry-run",
        "as_of_date": as_of.isoformat(),
        "root": root.as_posix(),
        "summary": {
            "entities": len(entities),
            "files_would_change": sum(item["would_change"] for item in changes),
            "files_changed": sum(item["would_change"] for item in changes) if write else 0,
            "downgraded_verified": sum(item["downgraded_verified"] for item in changes),
            "source_excerpt_review": sum(item["source_excerpt_review"] for item in changes),
            "unresolved_relations": sum(bool(item["unresolved_relations"]) for item in changes),
            "unresolved_authorities": sum(bool(item["unresolved_authorities"]) for item in changes),
            "parse_issues": len(parse_issues),
        },
        "parse_issues": parse_issues,
        "files": changes,
    }
    write_json(report, output)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--as-of-date", type=dt.date.fromisoformat, default=dt.date.today())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--write", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = migrate(args.root.resolve(), as_of=args.as_of_date, write=args.write, output=args.output)
    return 1 if report["summary"]["parse_issues"] else 0


if __name__ == "__main__":
    sys.exit(main())
