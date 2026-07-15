#!/usr/bin/env python3
"""Validate Wage Wiki frontmatter, graph links, provenance, and freshness."""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from authority_policy import authority_diagnostics
from claim_contract import validate_claim_anchors
from graph_contract import RELATED_FIELDS, RELATED_FIELD_TYPES
from kg_common import (
    SCHEMA_VERSION,
    URL_RE,
    as_list,
    entity_lookup,
    issue,
    load_entities,
    load_json,
    load_path_aliases,
    normalized_ref,
    parse_date,
    report_summary,
    resolve_entity_ref,
    scalar_text,
    severity_fails,
    wiki_targets,
    write_json,
)
from lint_sources import (
    _raw_index,
    _resolves_raw,
    _validate_raw_manifest,
    _validate_source_registry,
)
from log_contract import LOG_ACTIONS
from qa_catalog import validate_qa_catalog
from review_policy import review_deadline_passed
from schema_contract import SchemaContractError, load_schema_contract
from temporal_policy import supersession_diagnostics
from verification_contract import (
    VerifierRegistryError,
    has_verifier_identity,
    load_verifier_registry,
    validate_verification,
)
from verification_policy import verification_timeline_diagnostics


SOURCE_ENTITY_TYPES = {"rule", "case", "law", "interpretation"}
OFFICIAL_DOMAINS = ("law.go.kr", "scourt.go.kr", "moel.go.kr")
ENTITY_ID_RE = re.compile(r"^(?!(?:claim|evidence|source):)[^\s]+$")
EVIDENCE_FIELDS = frozenset(
    {"evidence_id", "source_id", "locator", "excerpt", "supports", "verified_on"}
)
RELATION_FIELDS = frozenset({"relation_type", "target_id", "target", "note"})
TEMPORAL_FIELDS = frozenset(
    {"applicable_from", "applicable_to", "rule_version", "transition_note"}
)


def _validate_list_of_strings(entity: Any, field: str, issues: list[dict[str, Any]]) -> None:
    if field not in entity.data:
        return
    value = entity.data.get(field)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        issues.append(issue("high", "FIELD_TYPE", entity.relative_path, f"{field} must be a list of strings", field))
    elif len(value) != len(set(value)):
        issues.append(issue("medium", "DUPLICATE_LIST_VALUE", entity.relative_path, f"{field} contains duplicate values", field))


def _validate_evidence(entity: Any, known_source_ids: set[str], issues: list[dict[str, Any]]) -> None:
    if "evidence" not in entity.data:
        return
    evidence = entity.data.get("evidence")
    if not isinstance(evidence, list):
        issues.append(issue("high", "EVIDENCE_TYPE", entity.relative_path, "evidence must be a list", "evidence"))
        return
    seen: set[str] = set()
    for index, record in enumerate(evidence):
        field = f"evidence[{index}]"
        if not isinstance(record, dict):
            issues.append(issue("high", "EVIDENCE_ITEM_TYPE", entity.relative_path, f"{field} must be a mapping", field))
            continue
        for unknown_field in sorted(set(record) - EVIDENCE_FIELDS):
            issues.append(
                issue(
                    "high",
                    "EVIDENCE_FIELD_UNKNOWN",
                    entity.relative_path,
                    f"{field} contains an unsupported field: {unknown_field}",
                    f"{field}.{unknown_field}",
                )
            )
        raw_evidence_id = record.get("evidence_id")
        raw_source_id = record.get("source_id")
        raw_locator = record.get("locator")
        evidence_id = (
            raw_evidence_id
            if isinstance(raw_evidence_id, str)
            and raw_evidence_id
            and raw_evidence_id == raw_evidence_id.strip()
            else ""
        )
        source_id = (
            raw_source_id
            if isinstance(raw_source_id, str)
            and raw_source_id
            and raw_source_id == raw_source_id.strip()
            else ""
        )
        locator = (
            raw_locator
            if isinstance(raw_locator, str)
            and raw_locator
            and raw_locator == raw_locator.strip()
            else ""
        )
        supports = record.get("supports")
        if not evidence_id:
            issues.append(issue("high", "EVIDENCE_ID", entity.relative_path, f"{field}.evidence_id must be a nonempty string", f"{field}.evidence_id"))
        elif evidence_id in seen:
            issues.append(issue("high", "EVIDENCE_ID", entity.relative_path, f"{field}.evidence_id is missing or duplicated", field))
        if evidence_id:
            seen.add(evidence_id)
        if not source_id:
            issues.append(issue("high", "EVIDENCE_SOURCE", entity.relative_path, f"{field}.source_id must be a nonempty string", f"{field}.source_id"))
        elif known_source_ids and source_id not in known_source_ids:
            issues.append(issue("high", "EVIDENCE_SOURCE_UNKNOWN", entity.relative_path, f"unknown source_id: {source_id}", field))
        if not locator:
            issues.append(issue("high", "EVIDENCE_LOCATOR", entity.relative_path, f"{field}.locator must be a nonempty string", f"{field}.locator"))
        if "excerpt" in record and not isinstance(record["excerpt"], str):
            issues.append(issue("high", "EVIDENCE_EXCERPT_TYPE", entity.relative_path, f"{field}.excerpt must be a string", f"{field}.excerpt"))
        if (
            not isinstance(supports, list)
            or not supports
            or any(
                not isinstance(item, str) or not item.strip() or item != item.strip()
                for item in supports
            )
        ):
            issues.append(issue("high", "EVIDENCE_SUPPORTS", entity.relative_path, f"{field}.supports must contain claim IDs", field))
        elif len(supports) != len(set(supports)):
            issues.append(issue("high", "EVIDENCE_SUPPORTS_DUPLICATE", entity.relative_path, f"{field}.supports must contain unique claim IDs", f"{field}.supports"))
        raw_verified_on = record.get("verified_on")
        if "verified_on" in record and not isinstance(raw_verified_on, str):
            issues.append(issue("high", "EVIDENCE_VERIFIED_ON_TYPE", entity.relative_path, f"{field}.verified_on must be a string", f"{field}.verified_on"))
        verified_on = raw_verified_on if isinstance(raw_verified_on, str) else ""
        if verified_on and not parse_date(verified_on):
            issues.append(issue("high", "DATE_INVALID", entity.relative_path, f"{field}.verified_on is not a valid date", field))


def _validate_relations(entity: Any, id_targets: dict[str, Any], relation_vocab: set[str], issues: list[dict[str, Any]]) -> None:
    if "relations" not in entity.data:
        return
    relations = entity.data.get("relations")
    if not isinstance(relations, list):
        issues.append(issue("high", "RELATIONS_TYPE", entity.relative_path, "relations must be a list", "relations"))
        return
    seen: set[tuple[str, str]] = set()
    for index, record in enumerate(relations):
        field = f"relations[{index}]"
        if not isinstance(record, dict):
            issues.append(issue("high", "RELATION_ITEM_TYPE", entity.relative_path, f"{field} must be a mapping", field))
            continue
        for unknown_field in sorted(set(record) - RELATION_FIELDS):
            issues.append(
                issue(
                    "high",
                    "RELATION_FIELD_UNKNOWN",
                    entity.relative_path,
                    f"{field} contains an unsupported field: {unknown_field}",
                    f"{field}.{unknown_field}",
                )
            )
        raw_relation_type = record.get("relation_type")
        raw_target_id = record.get("target_id")
        relation_type = raw_relation_type if isinstance(raw_relation_type, str) else ""
        target_id = (
            raw_target_id
            if isinstance(raw_target_id, str)
            and raw_target_id
            and raw_target_id == raw_target_id.strip()
            else ""
        )
        for optional_field in ("target", "note"):
            if optional_field in record and not isinstance(record[optional_field], str):
                issues.append(
                    issue(
                        "high",
                        "RELATION_FIELD_TYPE",
                        entity.relative_path,
                        f"{field}.{optional_field} must be a string",
                        f"{field}.{optional_field}",
                    )
                )
        if relation_type not in relation_vocab:
            issues.append(issue("high", "VOCAB_RELATION", entity.relative_path, f"invalid relation_type: {relation_type or '<empty>'}", field))
        if not target_id:
            issues.append(issue("high", "RELATION_TARGET", entity.relative_path, f"{field}.target_id must be a nonempty trimmed string", f"{field}.target_id"))
        elif target_id not in id_targets:
            issues.append(issue("critical", "RELATION_TARGET_BROKEN", entity.relative_path, f"unknown relation target_id: {target_id}", field))
        pair = (relation_type, target_id)
        if pair in seen:
            issues.append(issue("medium", "RELATION_DUPLICATE", entity.relative_path, f"duplicate relation: {relation_type} -> {target_id}", field))
        seen.add(pair)


def _validate_dates(entity: Any, today: dt.date, issues: list[dict[str, Any]]) -> None:
    for field in (
        "effective_from", "effective_to", "as_of_date", "last_checked", "last_verified", "last_updated",
        "superseded_date", "conflict_resolved_date", "decision_date", "law_revision_date",
        "promulgation_date", "enforcement_date", "issue_date",
    ):
        value = scalar_text(entity.data.get(field))
        if value and not parse_date(value):
            issues.append(issue("high", "DATE_INVALID", entity.relative_path, f"{field} is not a valid YYYY-MM-DD date", field))
    if scalar_text(entity.data.get("schema_version")) == SCHEMA_VERSION:
        for field in ("effective_from", "effective_to", "as_of_date", "last_updated"):
            if not scalar_text(entity.data.get(field)):
                issues.append(issue("high", "DATE_REQUIRED", entity.relative_path, f"required date is empty: {field}", field))
    start = parse_date(entity.data.get("effective_from"))
    end = parse_date(entity.data.get("effective_to"))
    if start and end and start > end:
        issues.append(issue("high", "TEMPORAL_ORDER", entity.relative_path, "effective_from is later than effective_to"))
    temporal = entity.data.get("temporal")
    if "temporal" in entity.data:
        if not isinstance(temporal, dict):
            issues.append(issue("high", "RULE_TEMPORAL_TYPE", entity.relative_path, "temporal must be a mapping", "temporal"))
        else:
            for unknown_field in sorted(set(temporal) - TEMPORAL_FIELDS):
                issues.append(
                    issue(
                        "high",
                        "RULE_TEMPORAL_FIELD_UNKNOWN",
                        entity.relative_path,
                        f"temporal contains an unsupported field: {unknown_field}",
                        f"temporal.{unknown_field}",
                    )
                )
            for required_field in sorted(TEMPORAL_FIELDS - set(temporal)):
                issues.append(
                    issue(
                        "high",
                        "RULE_TEMPORAL_FIELD_MISSING",
                        entity.relative_path,
                        f"temporal field is required: {required_field}",
                        f"temporal.{required_field}",
                    )
                )
            raw_from = temporal.get("applicable_from")
            raw_to = temporal.get("applicable_to")
            applicable_from = (
                parse_date(raw_from)
                if isinstance(raw_from, str)
                and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", raw_from)
                else None
            )
            applicable_to = (
                parse_date(raw_to)
                if isinstance(raw_to, str)
                and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", raw_to)
                else None
            )
            if not applicable_from or not applicable_to:
                issues.append(issue("high", "RULE_TEMPORAL_DATE", entity.relative_path, "temporal applicable dates are required strings in YYYY-MM-DD format", "temporal"))
            elif applicable_from > applicable_to:
                issues.append(issue("high", "RULE_TEMPORAL_ORDER", entity.relative_path, "temporal.applicable_from is later than applicable_to", "temporal"))
            rule_version = temporal.get("rule_version")
            if not isinstance(rule_version, str) or not rule_version.strip():
                issues.append(issue("high", "RULE_TEMPORAL_VERSION", entity.relative_path, "temporal.rule_version must be a nonempty string", "temporal.rule_version"))
            if "transition_note" in temporal and not isinstance(temporal["transition_note"], str):
                issues.append(issue("high", "RULE_TEMPORAL_NOTE_TYPE", entity.relative_path, "temporal.transition_note must be a string", "temporal.transition_note"))
    last_updated = parse_date(entity.data.get("last_updated"))
    last_verified = parse_date(entity.data.get("last_verified"))
    last_checked = parse_date(entity.data.get("last_checked"))
    if last_updated and last_verified and last_updated > last_verified and entity.data.get("status") == "verified":
        issues.append(issue("high", "VERIFICATION_OUTDATED", entity.relative_path, "verified document was updated after last_verified"))
    if last_updated and last_checked and last_updated > last_checked and entity.data.get("status") == "verified":
        issues.append(issue("high", "CHECK_OUTDATED", entity.relative_path, "verified document was updated after last_checked"))
    cycle = scalar_text(entity.data.get("review_cycle"))
    checked = last_checked or last_verified
    if checked and review_deadline_passed(checked, cycle, today):
        issues.append(issue("medium", "STALE_VERIFICATION", entity.relative_path, f"review_cycle {cycle} deadline has passed"))
    if entity.data.get("status") == "draft" and last_updated and (today - last_updated).days > 30:
        issues.append(issue("medium", "DRAFT_BACKLOG", entity.relative_path, "draft has not been updated for more than 30 days"))


def _validate_case_source_gate(entity: Any, raw_names: set[str], path_aliases: dict[str, str], issues: list[dict[str, Any]]) -> None:
    if entity.data.get("entity_type") != "case" or scalar_text(entity.data.get("schema_version")) != SCHEMA_VERSION:
        return
    availability = scalar_text(entity.data.get("source_availability"))
    note = scalar_text(entity.data.get("source_availability_note"))
    urls = [scalar_text(item) for item in as_list(entity.data.get("source_urls"))]
    raw_targets = wiki_targets(entity.data.get("related_raw"))
    case_number = re.sub(r"\s+", "", scalar_text(entity.data.get("case_number"))).casefold()
    own_raw = False
    for target in raw_targets:
        compact_target = re.sub(r"\s+", "", normalized_ref(target))
        if _resolves_raw(target, raw_names, path_aliases) and (not case_number or case_number in compact_target):
            own_raw = True
            break
    if availability not in {"available", "unavailable_official", "partial"}:
        issues.append(issue("high", "CASE_SOURCE_AVAILABILITY", entity.relative_path, "source_availability is required", "source_availability"))
    elif availability == "available" and not own_raw:
        issues.append(issue("high", "CASE_OWN_RAW_MISSING", entity.relative_path, "available case must link its own raw decision", "related_raw"))
    elif availability == "unavailable_official":
        has_official_search = any(any(domain in url.casefold() for domain in OFFICIAL_DOMAINS) for url in urls)
        if not note or not has_official_search:
            issues.append(issue("high", "CASE_RAW_EXCEPTION_EVIDENCE", entity.relative_path, "unavailable_official requires a note and an official search/result URL", "source_availability_note"))
    elif availability == "partial" and not note:
        issues.append(issue("high", "CASE_PARTIAL_NOTE", entity.relative_path, "partial source availability requires an explanatory note", "source_availability_note"))


def _validate_log_targets(root: Path, path_aliases: dict[str, str], issues: list[dict[str, Any]]) -> None:
    logs_root = root / "wiki" / "logs"
    if not logs_root.exists():
        return
    current_paths = {
        normalized_ref(path.relative_to(root).as_posix())
        for path in (root / "wiki").rglob("*.md")
        if path.is_file()
    }
    action_re = re.compile(r"^\s*Action:\s*(\S+)\s*$")
    target_re = re.compile(r"^\s*Target:\s*(.+?)\s*$")
    for log in logs_root.glob("*.md"):
        try:
            lines = log.read_text(encoding="utf-8-sig").splitlines()
        except (OSError, UnicodeError):
            continue
        for line_number, line in enumerate(lines, start=1):
            action_match = action_re.match(line)
            if action_match and action_match.group(1) not in LOG_ACTIONS:
                issues.append(
                    issue(
                        "high",
                        "LOG_ACTION_INVALID",
                        log.relative_to(root).as_posix(),
                        f"line {line_number}: unknown Action {action_match.group(1)}",
                        "Action",
                    )
                )
            match = target_re.match(line)
            if not match:
                continue
            targets = [part.strip().strip('"') for part in match.group(1).split(";")]
            for target in targets:
                if ".md" not in target.casefold() or not target.casefold().startswith("wiki/"):
                    continue
                normalized = normalized_ref(target)
                resolved = normalized in current_paths or path_aliases.get(normalized) in current_paths
                if not resolved:
                    issues.append(issue("low", "LOG_TARGET_UNRESOLVED", log.relative_to(root).as_posix(), f"line {line_number}: unresolved historical target {target}"))


def _validate_qa_regression(root: Path, id_targets: dict[str, Any], issues: list[dict[str, Any]]) -> None:
    path = root / "tests" / "qa_regression.jsonl"
    relative = path.relative_to(root).as_posix()
    mappings = {
        "QA_READ": ("critical", "QA_REGRESSION_READ"),
        "INVALID_JSON": ("critical", "QA_REGRESSION_JSON"),
        "INVALID_RECORD_TYPE": ("critical", "QA_REGRESSION_TYPE"),
        "MISSING_FIELDS": ("high", "QA_REGRESSION_FIELD"),
        "DUPLICATE_OR_EMPTY_ID": ("high", "QA_REGRESSION_ID"),
        "INVALID_AS_OF": ("high", "QA_REGRESSION_DATE"),
        "INVALID_ID_LIST": ("high", "QA_REGRESSION_ID_LIST"),
        "UNKNOWN_AUTHORITY_ID": ("critical", "QA_REGRESSION_ID_BROKEN"),
        "UNKNOWN_RULE_ID": ("critical", "QA_REGRESSION_ID_BROKEN"),
        "REQUIRED_ID_NOT_RULE": ("high", "QA_REGRESSION_ID_TYPE"),
        "INVALID_FORBIDDEN_CLAIMS": ("high", "QA_REGRESSION_FORBIDDEN"),
    }
    result = validate_qa_catalog(path, id_targets, missing_ok=True)
    for item in result["issues"]:
        severity, code = mappings.get(item["code"], ("high", "QA_REGRESSION_INVALID"))
        line = item.get("line", 0)
        prefix = f"line {line}: " if line else ""
        issues.append(
            issue(
                severity,
                code,
                relative,
                prefix + scalar_text(item.get("message")),
                scalar_text(item.get("field")),
            )
        )


def lint_repository(
    root: Path,
    today: dt.date | None = None,
    strict_v13: bool = False,
    require_claim_anchors: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    today = today or dt.date.today()
    entities, issues = load_entities(root)
    contract = None
    try:
        contract = load_schema_contract(root)
    except SchemaContractError as exc:
        issues.append(
            issue("critical", "SCHEMA_CONTRACT_READ", "schemas", str(exc))
        )
    if contract is not None:
        for problem in contract.problems:
            issues.append(
                issue(
                    "critical",
                    problem.code,
                    "schemas",
                    problem.message,
                    problem.field,
                )
            )
        vocab = contract.vocabulary
        relation_vocab = set(contract.relation_types)
        controlled_fields = {
            field: set(values)
            for field, values in contract.controlled_fields.items()
            if field != "verification_method"
        }
        verification_methods = set(contract.verification_methods)
        list_fields = set(contract.string_list_fields)
    else:
        vocab = load_json(root / "schemas" / "vocabularies.json", {})
        relation_vocab = set(vocab.get("relation_type", []))
        controlled_fields = {}
        raw_verification_methods = vocab.get("verification_method")
        verification_methods = (
            set(raw_verification_methods)
            if isinstance(raw_verification_methods, list)
            and raw_verification_methods
            and all(isinstance(value, str) for value in raw_verification_methods)
            else None
        )
        list_fields = set()
    verifier_ids: set[str] | None = None
    try:
        verifier_ids = set(load_verifier_registry(root).ids)
    except VerifierRegistryError as exc:
        issues.append(issue("critical", "VERIFIER_REGISTRY_READ", "schemas/verifiers.json", str(exc)))
    by_id, names = entity_lookup(entities)
    path_aliases = load_path_aliases(root)
    raw_names = _raw_index(root)
    registry_ids = _validate_source_registry(root, issues)
    manifest_ids = _validate_raw_manifest(root, issues)
    known_source_ids = registry_ids | manifest_ids

    id_groups: dict[str, list[Any]] = defaultdict(list)
    id_targets: dict[str, Any] = {}
    alias_groups: dict[str, list[Any]] = defaultdict(list)
    for entity in entities:
        entity_id = scalar_text(entity.data.get("id"))
        if entity_id:
            id_groups[entity_id].append(entity)
            id_targets.setdefault(entity_id, entity)
        for alias in as_list(entity.data.get("id_aliases")):
            alias_text = scalar_text(alias)
            if alias_text:
                alias_groups[alias_text].append(entity)
                id_targets.setdefault(alias_text, entity)
    for entity_id, group in id_groups.items():
        if len(group) > 1:
            for entity in group:
                issues.append(issue("critical", "DUPLICATE_ID", entity.relative_path, f"duplicate id: {entity_id}", "id"))
    for alias, group in alias_groups.items():
        if alias in id_groups or len(group) > 1:
            for entity in group:
                issues.append(issue("critical", "ID_ALIAS_COLLISION", entity.relative_path, f"id_alias collision: {alias}", "id_aliases"))
    global_aliases = load_json(root / "schemas" / "id-aliases.json", {}).get("aliases_to_canonical", {})
    if not isinstance(global_aliases, dict):
        issues.append(issue("critical", "ID_ALIAS_MAP_TYPE", "schemas/id-aliases.json", "aliases_to_canonical must be an object"))
        global_aliases = {}
    global_alias_map = {
        scalar_text(alias): scalar_text(canonical)
        for alias, canonical in global_aliases.items()
        if scalar_text(alias)
    }
    for alias, group in alias_groups.items():
        if len(group) != 1 or alias in id_groups:
            continue
        canonical = scalar_text(group[0].data.get("id"))
        if global_alias_map.get(alias) != canonical:
            issues.append(
                issue(
                    "high",
                    "ID_ALIAS_MAP_DRIFT",
                    group[0].relative_path,
                    f"frontmatter alias is not mapped to its canonical ID in schemas/id-aliases.json: {alias}",
                    "id_aliases",
                )
            )
    for alias_text, canonical_text in global_alias_map.items():
        target = by_id.get(canonical_text)
        if target is None:
            issues.append(issue("critical", "ID_ALIAS_CANONICAL_BROKEN", "schemas/id-aliases.json", f"unknown canonical ID for {alias_text}: {canonical_text}"))
            continue
        collision = id_targets.get(alias_text)
        if collision is not None and collision is not target:
            issues.append(issue("critical", "ID_ALIAS_COLLISION", "schemas/id-aliases.json", f"global alias collides with another entity: {alias_text}"))
            continue
        if alias_text not in {scalar_text(value) for value in as_list(target.data.get("id_aliases"))}:
            issues.append(
                issue(
                    "high",
                    "ID_ALIAS_FRONTMATTER_DRIFT",
                    "schemas/id-aliases.json",
                    f"global alias is missing from canonical entity frontmatter: {alias_text}",
                    "aliases_to_canonical",
                )
            )
        id_targets[alias_text] = target
        key = normalized_ref(alias_text)
        if target not in names[key]:
            names[key].append(target)

    for entity in entities:
        data = entity.data
        entity_type = scalar_text(data.get("entity_type"))
        version = scalar_text(data.get("schema_version"))
        if version != SCHEMA_VERSION:
            severity = "high" if strict_v13 else "medium"
            issues.append(issue(severity, "SCHEMA_MIGRATION_REQUIRED", entity.relative_path, f"schema_version is {version or '<missing>'}; expected {SCHEMA_VERSION}", "schema_version"))
        elif contract is not None:
            required_fields = contract.required_fields | contract.required_by_entity_type.get(
                entity_type, frozenset()
            )
            for field in sorted(required_fields):
                if field not in data:
                    issues.append(issue("high", "V13_FIELD_MISSING", entity.relative_path, f"required v1.3 field is missing: {field}", field))
        entity_id_value = data.get("id")
        if not isinstance(entity_id_value, str) or not entity_id_value:
            issues.append(issue("critical", "ID_MISSING", entity.relative_path, "id is required", "id"))
        elif not ENTITY_ID_RE.fullmatch(entity_id_value):
            issues.append(issue("critical", "ID_INVALID", entity.relative_path, "id contains whitespace or uses a reserved graph namespace", "id"))
        if not scalar_text(data.get("title")):
            issues.append(issue("high", "TITLE_MISSING", entity.relative_path, "title is required", "title"))
        for field in list_fields:
            _validate_list_of_strings(entity, field, issues)
        for source_url in as_list(data.get("source_urls")):
            if not isinstance(source_url, str) or not URL_RE.match(source_url.strip()):
                issues.append(issue("high", "SOURCE_URL_INVALID", entity.relative_path, f"source_urls entry must be http(s): {source_url}", "source_urls"))
        for field, allowed in controlled_fields.items():
            if field not in data:
                continue
            values = as_list(data.get(field)) if field in list_fields else [data.get(field)]
            for value in values:
                text = scalar_text(value)
                if text and text not in allowed:
                    legacy_status = field == "status" and text in set(vocab.get("legacy_status_aliases", []))
                    issues.append(issue("medium" if legacy_status else "high", "VOCAB_INVALID", entity.relative_path, f"invalid {field}: {text}", field))
        if data.get("status") == "verified":
            if data.get("ingestion_status") != "verified":
                issues.append(issue("high", "STATUS_INGESTION_MISMATCH", entity.relative_path, "verified status requires verified ingestion_status"))
            if not scalar_text(data.get("last_verified")):
                issues.append(issue("high", "VERIFIED_DATE_MISSING", entity.relative_path, "verified status requires last_verified"))
            if version == SCHEMA_VERSION and not scalar_text(data.get("last_checked")):
                issues.append(issue("high", "CHECK_DATE_MISSING", entity.relative_path, "verified v1.3 status requires last_checked", "last_checked"))
            if version == SCHEMA_VERSION and not has_verifier_identity(data):
                issues.append(issue("high", "VERIFIER_MISSING", entity.relative_path, "verified status requires a nonblank structured or legacy verifier identity", "verification"))
        legal_status = scalar_text(data.get("legal_status"))
        if legal_status in {"superseded", "overruled"}:
            if not scalar_text(data.get("superseded_by")) or not scalar_text(data.get("superseded_date")):
                issues.append(issue("high", "SUPERSESSION_INCOMPLETE", entity.relative_path, "superseded/overruled entity requires superseded_by and superseded_date"))
        if scalar_text(data.get("superseded_by")) and legal_status not in {"superseded", "overruled"}:
            issues.append(issue("high", "SUPERSESSION_STATUS", entity.relative_path, "superseded_by conflicts with legal_status"))
        if scalar_text(data.get("superseded_date")) and legal_status not in {"superseded", "overruled"}:
            issues.append(issue("high", "SUPERSESSION_STATUS", entity.relative_path, "superseded_date conflicts with legal_status"))
        for diagnostic in supersession_diagnostics(data, id_targets):
            issues.append(issue(diagnostic.severity, diagnostic.code, entity.relative_path, diagnostic.message, diagnostic.field))
        conflict_status = scalar_text(data.get("conflict_status"))
        resolution = scalar_text(data.get("conflict_resolution"))
        if conflict_status == "active" and resolution not in {"pending", "resolved", "unresolvable"}:
            issues.append(issue("high", "CONFLICT_RESOLUTION_MISSING", entity.relative_path, "active conflict requires conflict_resolution"))
        if resolution == "resolved" and not scalar_text(data.get("conflict_resolved_date")):
            issues.append(issue("high", "CONFLICT_DATE_MISSING", entity.relative_path, "resolved conflict requires conflict_resolved_date"))

        links_present = False
        for field in RELATED_FIELDS:
            for target in wiki_targets(data.get(field)):
                links_present = True
                matches = resolve_entity_ref(target, names)
                if not matches:
                    issues.append(issue("critical", "BROKEN_REFERENCE", entity.relative_path, f"{field} target does not exist: {target}", field))
                elif len(matches) > 1:
                    issues.append(issue("high", "AMBIGUOUS_REFERENCE", entity.relative_path, f"{field} target is ambiguous: {target}", field))
                else:
                    actual_type = scalar_text(matches[0].data.get("entity_type"))
                    expected_type = RELATED_FIELD_TYPES[field]
                    if actual_type != expected_type:
                        issues.append(
                            issue(
                                "high",
                                "REFERENCE_TYPE_MISMATCH",
                                entity.relative_path,
                                f"{field} requires {expected_type}, but {target} resolves to {actual_type or '<missing>'}",
                                field,
                            )
                        )
        relation_records = data.get("relations")
        if isinstance(relation_records, list) and relation_records:
            links_present = True
        if not links_present:
            issues.append(issue("high", "ORPHAN_ENTITY", entity.relative_path, "entity has no graph relation"))
        for raw_item in as_list(data.get("related_raw")):
            text = scalar_text(raw_item)
            if URL_RE.match(text):
                issues.append(issue("medium", "SOURCE_URL_IN_RELATED_RAW", entity.relative_path, "external URL belongs in source_urls", "related_raw"))
                continue
            for target in wiki_targets(text):
                if not _resolves_raw(target, raw_names, path_aliases):
                    issues.append(issue("critical", "BROKEN_RAW_REFERENCE", entity.relative_path, f"raw target does not exist: {target}", "related_raw"))

        for authority_field in ("primary_authority_id", "authority_ids"):
            for authority_id in as_list(data.get(authority_field)):
                authority_text = scalar_text(authority_id)
                if authority_text and authority_text not in id_targets:
                    issues.append(issue("critical", "AUTHORITY_ID_BROKEN", entity.relative_path, f"unknown authority ID: {authority_text}", authority_field))
        if entity_type == "rule" and not scalar_text(data.get("primary_authority")) and not as_list(data.get("authority_ids")):
            issues.append(issue("critical", "RULE_WITHOUT_AUTHORITY", entity.relative_path, "rule has no primary authority"))
        if entity_type == "rule" and not (as_list(data.get("related_cases")) or as_list(data.get("related_laws")) or as_list(data.get("related_interpretations"))):
            issues.append(issue("critical", "RULE_AUTHORITY_LINK_MISSING", entity.relative_path, "rule must link a case, law, or interpretation"))
        for diagnostic in authority_diagnostics(data, id_targets):
            issues.append(issue(diagnostic.severity, diagnostic.code, entity.relative_path, diagnostic.message, diagnostic.field))
        if entity_type == "case" and (not scalar_text(data.get("holding_summary")) or not as_list(data.get("legal_principles"))):
            issues.append(issue("high", "CASE_HOLDING_MISSING", entity.relative_path, "case requires holding_summary and legal_principles"))
        if entity_type == "case" and version == SCHEMA_VERSION:
            for field in ("court_name", "case_number", "decision_date", "case_role"):
                if not scalar_text(data.get(field)):
                    issues.append(issue("high", "CASE_FIELD_EMPTY", entity.relative_path, f"case field is required: {field}", field))
        if entity_type in {"concept", "fact_pattern"} and not as_list(data.get("related_rules")):
            issues.append(issue("medium", "RULE_LINK_MISSING", entity.relative_path, f"{entity_type} requires a related rule"))
        if entity_type == "rule" and version == SCHEMA_VERSION:
            for field in ("issue", "elements", "exceptions", "conclusion", "temporal", "decision_factors"):
                if field not in data:
                    issues.append(issue("high", "RULE_FIELD_MISSING", entity.relative_path, f"rule field is missing: {field}", field))
            for field in ("issue", "conclusion", "law_version", "extinction_period"):
                if not scalar_text(data.get(field)):
                    issues.append(issue("high", "RULE_FIELD_EMPTY", entity.relative_path, f"rule field must be explicit; use '해당 없음' when inapplicable: {field}", field))
            if not as_list(data.get("elements")):
                issues.append(issue("high", "RULE_ELEMENTS_EMPTY", entity.relative_path, "rule elements must identify at least one decision element", "elements"))
        if entity_type == "interpretation" and version == SCHEMA_VERSION:
            for field in ("issuing_agency", "document_number", "issue_date", "interpretation_type", "legal_effect"):
                if not scalar_text(data.get(field)):
                    issues.append(issue("high", "INTERPRETATION_FIELD_MISSING", entity.relative_path, f"interpretation field is missing: {field}", field))
        if entity_type == "law" and version == SCHEMA_VERSION:
            for field in ("law_version", "law_revision_date", "promulgation_date", "enforcement_date"):
                if not scalar_text(data.get(field)):
                    issues.append(issue("high", "LAW_FIELD_EMPTY", entity.relative_path, f"law field is required: {field}", field))
        if entity_type in SOURCE_ENTITY_TYPES and not (
            as_list(data.get("related_raw")) or as_list(data.get("source_urls")) or as_list(data.get("evidence"))
        ):
            unavailable_exception = entity_type == "case" and data.get("source_availability") == "unavailable_official"
            if not unavailable_exception:
                issues.append(issue("high", "SOURCE_MISSING", entity.relative_path, "authority entity has no source"))
        if version == SCHEMA_VERSION and data.get("status") == "verified" and entity_type in SOURCE_ENTITY_TYPES and not as_list(data.get("evidence")):
            issues.append(issue("high", "EVIDENCE_MISSING", entity.relative_path, "verified authority entity requires claim-level evidence", "evidence"))
        _validate_evidence(entity, known_source_ids, issues)
        for problem in validate_claim_anchors(data, entity.body, require_anchors=require_claim_anchors):
            issues.append(issue(problem.severity, problem.code, entity.relative_path, problem.message, problem.field))
        for problem in validate_verification(data, verifier_ids, verification_methods):
            issues.append(issue(problem.severity, problem.code, entity.relative_path, problem.message, problem.field))
        _validate_relations(entity, id_targets, relation_vocab, issues)
        _validate_dates(entity, today, issues)
        for diagnostic in verification_timeline_diagnostics(
            data,
            today,
            source_entity=entity_type in SOURCE_ENTITY_TYPES,
        ):
            issues.append(issue(diagnostic.severity, diagnostic.code, entity.relative_path, diagnostic.message, diagnostic.field))
        _validate_case_source_gate(entity, raw_names, path_aliases, issues)

    _validate_log_targets(root, path_aliases, issues)
    _validate_qa_regression(root, id_targets, issues)
    order = {severity: index for index, severity in enumerate(("critical", "high", "medium", "low", "info"))}
    issues.sort(key=lambda item: (order.get(item["severity"], 99), item["code"], item["path"], item["message"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "as_of_date": today.isoformat(),
        "root": root.as_posix(),
        "summary": report_summary(issues, len(entities)),
        "issues": issues,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, help="write JSON report here; stdout when omitted")
    parser.add_argument("--today", type=dt.date.fromisoformat, help="deterministic check date (YYYY-MM-DD)")
    parser.add_argument("--strict-v13", action="store_true", help="treat unmigrated documents as high severity")
    parser.add_argument("--require-claim-anchors", action="store_true", help="require every evidence supports ID to resolve to a body ^claim-id block")
    parser.add_argument("--fail-on", choices=("critical", "high", "medium", "low", "info", "none"), default="critical")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = lint_repository(
        args.root,
        today=args.today,
        strict_v13=args.strict_v13,
        require_claim_anchors=args.require_claim_anchors,
    )
    write_json(report, args.output)
    return 1 if severity_fails(report["issues"], args.fail_on) else 0


if __name__ == "__main__":
    sys.exit(main())
