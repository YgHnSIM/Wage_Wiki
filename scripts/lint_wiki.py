#!/usr/bin/env python3
"""Validate Wage Wiki frontmatter, graph links, provenance, and freshness."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from kg_common import (
    FrontmatterError,
    SCHEMA_VERSION,
    URL_RE,
    _SubsetYamlParser,
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


COMMON_V13_FIELDS = (
    "schema_version",
    "jurisdiction",
    "legal_status",
    "as_of_date",
    "last_checked",
    "verified_by",
    "aliases",
    "id_aliases",
    "primary_authority_id",
    "authority_ids",
    "source_urls",
    "evidence",
    "relations",
)
RELATED_FIELDS = (
    "related_concepts",
    "related_rules",
    "related_cases",
    "related_laws",
    "related_interpretations",
    "related_fact_patterns",
)
SOURCE_ENTITY_TYPES = {"rule", "case", "law", "interpretation"}
OFFICIAL_DOMAINS = ("law.go.kr", "scourt.go.kr", "moel.go.kr")


def _raw_index(root: Path) -> set[str]:
    result: set[str] = set()
    raw_root = root / "raw"
    if not raw_root.exists():
        return result
    for path in raw_root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        for candidate in (relative, relative.removeprefix("raw/"), path.name, path.stem):
            result.add(normalized_ref(candidate))
    return result


def _validate_source_registry(root: Path, issues: list[dict[str, Any]]) -> set[str]:
    path = root / "sources" / "registry.yaml"
    relative = path.relative_to(root).as_posix()
    if not path.exists():
        issues.append(issue("high", "SOURCE_REGISTRY_MISSING", relative, "source registry does not exist"))
        return set()
    try:
        data = _SubsetYamlParser(path.read_text(encoding="utf-8-sig")).parse()
    except (OSError, UnicodeError, FrontmatterError) as exc:
        issues.append(issue("critical", "SOURCE_REGISTRY_PARSE", relative, str(exc)))
        return set()
    records = data.get("sources")
    if not isinstance(records, list):
        issues.append(issue("critical", "SOURCE_REGISTRY_TYPE", relative, "sources must be a list"))
        return set()
    ids: set[str] = set()
    paths: dict[str, str] = {}
    for index, record in enumerate(records):
        field = f"sources[{index}]"
        if not isinstance(record, dict):
            issues.append(issue("high", "SOURCE_REGISTRY_RECORD", relative, f"{field} must be a mapping"))
            continue
        source_id = scalar_text(record.get("source_id"))
        if not source_id or source_id in ids:
            issues.append(issue("critical", "SOURCE_REGISTRY_ID", relative, f"{field}.source_id is missing or duplicated"))
        if source_id:
            ids.add(source_id)
        source_path = scalar_text(record.get("path"))
        if source_path:
            normalized = normalized_ref(source_path)
            if normalized in paths and paths[normalized] != source_id:
                issues.append(issue("critical", "SOURCE_REGISTRY_PATH_DUPLICATE", relative, f"path has multiple source IDs: {source_path}"))
            paths[normalized] = source_id
            resolved = (root / source_path).resolve()
            try:
                resolved.relative_to(root)
            except ValueError:
                issues.append(issue("critical", "SOURCE_REGISTRY_PATH_ESCAPE", relative, f"path escapes repository: {source_path}"))
            else:
                if not resolved.is_file():
                    issues.append(issue("critical", "SOURCE_REGISTRY_PATH_BROKEN", relative, f"source path does not exist: {source_path}"))
                elif not normalized.startswith("raw/"):
                    issues.append(issue("high", "SOURCE_REGISTRY_PATH_SCOPE", relative, f"source path must be under raw/: {source_path}"))
    return ids


def _validate_raw_manifest(root: Path, issues: list[dict[str, Any]]) -> set[str]:
    path = root / "sources" / "raw-manifest.jsonl"
    relative = path.relative_to(root).as_posix()
    if not path.exists():
        issues.append(issue("high", "RAW_MANIFEST_MISSING", relative, "generate the committed raw manifest"))
        return set()
    records: list[dict[str, Any]] = []
    try:
        for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError(f"line {line_number}: record must be an object")
            records.append(record)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        issues.append(issue("critical", "RAW_MANIFEST_PARSE", relative, str(exc)))
        return set()
    manifest_paths = [scalar_text(record.get("path")) for record in records]
    source_ids = [scalar_text(record.get("source_id")) for record in records]
    if any(not value for value in manifest_paths) or len(manifest_paths) != len(set(manifest_paths)):
        issues.append(issue("critical", "RAW_MANIFEST_PATH", relative, "manifest paths are missing or duplicated"))
    if any(not value for value in source_ids) or len(source_ids) != len(set(source_ids)):
        issues.append(issue("critical", "RAW_MANIFEST_SOURCE_ID", relative, "manifest source IDs are missing or duplicated; check raw deduplication and registry"))
    try:
        from build_manifest import build_manifest

        actual = build_manifest(root)
    except (OSError, UnicodeError) as exc:
        issues.append(issue("critical", "RAW_MANIFEST_BUILD", relative, str(exc)))
        return set(source_ids)
    expected_render = [json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records]
    actual_render = [json.dumps(record, ensure_ascii=False, sort_keys=True) for record in actual]
    if expected_render != actual_render:
        expected_by_path = {scalar_text(record.get("path")): record for record in records}
        actual_by_path = {scalar_text(record.get("path")): record for record in actual}
        added = sorted(set(actual_by_path) - set(expected_by_path))
        removed = sorted(set(expected_by_path) - set(actual_by_path))
        changed = sorted(path_key for path_key in set(actual_by_path) & set(expected_by_path) if actual_by_path[path_key] != expected_by_path[path_key])
        issues.append(issue("critical", "RAW_MANIFEST_STALE", relative, f"manifest differs: added={len(added)}, removed={len(removed)}, changed={len(changed)}"))
    return set(source_ids)


def _resolves_raw(target: str, raw_names: set[str], path_aliases: dict[str, str]) -> bool:
    normalized = normalized_ref(target)
    candidates = {normalized, normalized_ref(Path(normalized).name)}
    for candidate in tuple(candidates):
        if candidate in path_aliases:
            candidates.add(path_aliases[candidate])
            candidates.add(normalized_ref(Path(path_aliases[candidate]).name))
    return any(candidate in raw_names for candidate in candidates)


def _authority_levels(entity: Any, by_id: dict[str, Any]) -> set[int]:
    levels: set[int] = set()
    text = scalar_text(entity.data.get("primary_authority"))
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
    primary_authority_id = scalar_text(entity.data.get("primary_authority_id"))
    target = by_id.get(primary_authority_id)
    if target and isinstance(target.data.get("authority_level"), int):
        levels.add(target.data["authority_level"])
    if entity.data.get("entity_type") == "law":
        levels.add(1)
    elif entity.data.get("entity_type") == "interpretation":
        levels.add(5)
    return levels


def _validate_list_of_strings(entity: Any, field: str, issues: list[dict[str, Any]]) -> None:
    value = entity.data.get(field)
    if value is None:
        return
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        issues.append(issue("high", "FIELD_TYPE", entity.relative_path, f"{field} must be a list of strings", field))
    elif len(value) != len(set(value)):
        issues.append(issue("medium", "DUPLICATE_LIST_VALUE", entity.relative_path, f"{field} contains duplicate values", field))


def _validate_evidence(entity: Any, known_source_ids: set[str], issues: list[dict[str, Any]]) -> None:
    evidence = entity.data.get("evidence")
    if evidence is None:
        return
    if not isinstance(evidence, list):
        issues.append(issue("high", "EVIDENCE_TYPE", entity.relative_path, "evidence must be a list", "evidence"))
        return
    seen: set[str] = set()
    for index, record in enumerate(evidence):
        field = f"evidence[{index}]"
        if not isinstance(record, dict):
            issues.append(issue("high", "EVIDENCE_ITEM_TYPE", entity.relative_path, f"{field} must be a mapping", field))
            continue
        evidence_id = scalar_text(record.get("evidence_id"))
        source_id = scalar_text(record.get("source_id"))
        locator = scalar_text(record.get("locator"))
        supports = record.get("supports")
        if not evidence_id or evidence_id in seen:
            issues.append(issue("high", "EVIDENCE_ID", entity.relative_path, f"{field}.evidence_id is missing or duplicated", field))
        seen.add(evidence_id)
        if not source_id:
            issues.append(issue("high", "EVIDENCE_SOURCE", entity.relative_path, f"{field}.source_id is required", field))
        elif known_source_ids and source_id not in known_source_ids:
            issues.append(issue("high", "EVIDENCE_SOURCE_UNKNOWN", entity.relative_path, f"unknown source_id: {source_id}", field))
        if not locator:
            issues.append(issue("high", "EVIDENCE_LOCATOR", entity.relative_path, f"{field}.locator is required", field))
        if not isinstance(supports, list) or not supports or any(not scalar_text(item) for item in supports):
            issues.append(issue("high", "EVIDENCE_SUPPORTS", entity.relative_path, f"{field}.supports must contain claim IDs", field))
        verified_on = scalar_text(record.get("verified_on"))
        if verified_on and not parse_date(verified_on):
            issues.append(issue("medium", "DATE_INVALID", entity.relative_path, f"{field}.verified_on is not a valid date", field))


def _validate_relations(entity: Any, id_targets: dict[str, Any], relation_vocab: set[str], issues: list[dict[str, Any]]) -> None:
    relations = entity.data.get("relations")
    if relations is None:
        return
    if not isinstance(relations, list):
        issues.append(issue("high", "RELATIONS_TYPE", entity.relative_path, "relations must be a list", "relations"))
        return
    seen: set[tuple[str, str]] = set()
    for index, record in enumerate(relations):
        field = f"relations[{index}]"
        if not isinstance(record, dict):
            issues.append(issue("high", "RELATION_ITEM_TYPE", entity.relative_path, f"{field} must be a mapping", field))
            continue
        relation_type = scalar_text(record.get("relation_type"))
        target_id = scalar_text(record.get("target_id"))
        if relation_type not in relation_vocab:
            issues.append(issue("high", "VOCAB_RELATION", entity.relative_path, f"invalid relation_type: {relation_type or '<empty>'}", field))
        if not target_id:
            issues.append(issue("high", "RELATION_TARGET", entity.relative_path, f"{field}.target_id is required", field))
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
    if isinstance(temporal, dict):
        applicable_from = parse_date(temporal.get("applicable_from"))
        applicable_to = parse_date(temporal.get("applicable_to"))
        if not applicable_from or not applicable_to:
            issues.append(issue("high", "RULE_TEMPORAL_DATE", entity.relative_path, "temporal applicable dates are required and must be valid", "temporal"))
        elif applicable_from > applicable_to:
            issues.append(issue("high", "RULE_TEMPORAL_ORDER", entity.relative_path, "temporal.applicable_from is later than applicable_to", "temporal"))
    last_updated = parse_date(entity.data.get("last_updated"))
    last_verified = parse_date(entity.data.get("last_verified"))
    last_checked = parse_date(entity.data.get("last_checked"))
    if last_updated and last_verified and last_updated > last_verified and entity.data.get("status") == "verified":
        issues.append(issue("high", "VERIFICATION_OUTDATED", entity.relative_path, "verified document was updated after last_verified"))
    if last_updated and last_checked and last_updated > last_checked and entity.data.get("status") == "verified":
        issues.append(issue("high", "CHECK_OUTDATED", entity.relative_path, "verified document was updated after last_checked"))
    cycle_days = {"monthly": 31, "quarterly": 92, "annual": 366}
    cycle = scalar_text(entity.data.get("review_cycle"))
    checked = last_checked or last_verified
    if checked and cycle in cycle_days and (today - checked).days > cycle_days[cycle]:
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
    target_re = re.compile(r"^\s*Target:\s*(.+?)\s*$")
    for log in logs_root.glob("*.md"):
        try:
            lines = log.read_text(encoding="utf-8-sig").splitlines()
        except (OSError, UnicodeError):
            continue
        for line_number, line in enumerate(lines, start=1):
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
    if not path.exists():
        return
    seen: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError) as exc:
        issues.append(issue("critical", "QA_REGRESSION_READ", path.relative_to(root).as_posix(), str(exc)))
        return
    required_fields = {"id", "as_of", "question", "expected", "required_authority_ids", "required_rule_ids", "forbidden_claims"}
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            issues.append(issue("critical", "QA_REGRESSION_JSON", path.relative_to(root).as_posix(), f"line {line_number}: {exc.msg}"))
            continue
        if not isinstance(record, dict):
            issues.append(issue("critical", "QA_REGRESSION_TYPE", path.relative_to(root).as_posix(), f"line {line_number}: record must be an object"))
            continue
        missing = sorted(required_fields - set(record))
        if missing:
            issues.append(issue("high", "QA_REGRESSION_FIELD", path.relative_to(root).as_posix(), f"line {line_number}: missing {missing}"))
        test_id = scalar_text(record.get("id"))
        if not test_id or test_id in seen:
            issues.append(issue("high", "QA_REGRESSION_ID", path.relative_to(root).as_posix(), f"line {line_number}: missing or duplicate test id"))
        seen.add(test_id)
        if not parse_date(record.get("as_of")):
            issues.append(issue("high", "QA_REGRESSION_DATE", path.relative_to(root).as_posix(), f"line {line_number}: invalid as_of date"))
        for field, expected_type in (("required_authority_ids", "authority"), ("required_rule_ids", "rule")):
            values = record.get(field)
            if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
                issues.append(issue("high", "QA_REGRESSION_ID_LIST", path.relative_to(root).as_posix(), f"line {line_number}: {field} must be a string list"))
                continue
            for required_id in values:
                target = id_targets.get(required_id)
                if target is None:
                    issues.append(issue("critical", "QA_REGRESSION_ID_BROKEN", path.relative_to(root).as_posix(), f"line {line_number}: unknown required ID {required_id}"))
                elif expected_type == "rule" and target.data.get("entity_type") != "rule":
                    issues.append(issue("high", "QA_REGRESSION_ID_TYPE", path.relative_to(root).as_posix(), f"line {line_number}: {required_id} is not a rule"))
        forbidden = record.get("forbidden_claims")
        if not isinstance(forbidden, list) or not forbidden or any(not scalar_text(value) for value in forbidden):
            issues.append(issue("high", "QA_REGRESSION_FORBIDDEN", path.relative_to(root).as_posix(), f"line {line_number}: forbidden_claims must be a non-empty string list"))


def lint_repository(root: Path, today: dt.date | None = None, strict_v13: bool = False) -> dict[str, Any]:
    root = root.resolve()
    today = today or dt.date.today()
    entities, issues = load_entities(root)
    vocab = load_json(root / "schemas" / "vocabularies.json", {})
    relation_vocab = set(vocab.get("relation_type", []))
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
    for alias, canonical in global_aliases.items():
        alias_text, canonical_text = scalar_text(alias), scalar_text(canonical)
        target = by_id.get(canonical_text)
        if target is None:
            issues.append(issue("critical", "ID_ALIAS_CANONICAL_BROKEN", "schemas/id-aliases.json", f"unknown canonical ID for {alias_text}: {canonical_text}"))
            continue
        collision = id_targets.get(alias_text)
        if collision is not None and collision is not target:
            issues.append(issue("critical", "ID_ALIAS_COLLISION", "schemas/id-aliases.json", f"global alias collides with another entity: {alias_text}"))
            continue
        id_targets[alias_text] = target
        key = normalized_ref(alias_text)
        if target not in names[key]:
            names[key].append(target)

    controlled_fields = {
        key: set(value)
        for key, value in vocab.items()
        if isinstance(value, list) and key not in {"legacy_status_aliases", "historical_only_wage_criteria"}
    }
    list_fields = {
        "aliases", "id_aliases", "verified_by", "authority_ids", "source_urls", "review_trigger",
        "related_concepts", "related_rules", "related_cases", "related_laws", "related_interpretations",
        "related_fact_patterns", "related_raw", "source_excerpt", "legal_principles", "elements", "exceptions",
        "wage_criteria", "decision_factors", "wage_type",
    }
    for entity in entities:
        data = entity.data
        entity_type = scalar_text(data.get("entity_type"))
        version = scalar_text(data.get("schema_version"))
        if version != SCHEMA_VERSION:
            severity = "high" if strict_v13 else "medium"
            issues.append(issue(severity, "SCHEMA_MIGRATION_REQUIRED", entity.relative_path, f"schema_version is {version or '<missing>'}; expected {SCHEMA_VERSION}", "schema_version"))
        else:
            for field in COMMON_V13_FIELDS:
                if field not in data:
                    issues.append(issue("high", "V13_FIELD_MISSING", entity.relative_path, f"required v1.3 field is missing: {field}", field))
        if not scalar_text(data.get("id")):
            issues.append(issue("critical", "ID_MISSING", entity.relative_path, "id is required", "id"))
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
            values = as_list(data.get(field)) if field in {"wage_criteria", "wage_type"} else [data.get(field)]
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
            if version == SCHEMA_VERSION and not as_list(data.get("verified_by")):
                issues.append(issue("high", "VERIFIER_MISSING", entity.relative_path, "verified status requires verified_by", "verified_by"))
        legal_status = scalar_text(data.get("legal_status"))
        if legal_status in {"superseded", "overruled"}:
            if not scalar_text(data.get("superseded_by")) or not scalar_text(data.get("superseded_date")):
                issues.append(issue("high", "SUPERSESSION_INCOMPLETE", entity.relative_path, "superseded/overruled entity requires superseded_by and superseded_date"))
        if scalar_text(data.get("superseded_by")) and legal_status not in {"superseded", "overruled"}:
            issues.append(issue("high", "SUPERSESSION_STATUS", entity.relative_path, "superseded_by conflicts with legal_status"))
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
        actual_level = data.get("authority_level")
        expected_levels = _authority_levels(entity, by_id)
        if isinstance(actual_level, int) and expected_levels and actual_level not in expected_levels:
            issues.append(issue("high", "AUTHORITY_MISMATCH", entity.relative_path, f"authority_level {actual_level} conflicts with inferred levels {sorted(expected_levels)}", "authority_level"))
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
            if not isinstance(data.get("temporal"), dict):
                issues.append(issue("high", "RULE_TEMPORAL_TYPE", entity.relative_path, "temporal must be a mapping", "temporal"))
            elif not scalar_text(data["temporal"].get("rule_version")):
                issues.append(issue("high", "RULE_TEMPORAL_VERSION", entity.relative_path, "temporal.rule_version must be explicit", "temporal"))
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
        _validate_relations(entity, id_targets, relation_vocab, issues)
        _validate_dates(entity, today, issues)
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
    parser.add_argument("--fail-on", choices=("critical", "high", "medium", "low", "info", "none"), default="critical")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = lint_repository(args.root, today=args.today, strict_v13=args.strict_v13)
    write_json(report, args.output)
    return 1 if severity_fails(report["issues"], args.fail_on) else 0


if __name__ == "__main__":
    sys.exit(main())
