#!/usr/bin/env python3
"""Plan or apply a conservative v1.2 -> v1.3 frontmatter migration.

Dry-run is the default.  Files are changed only when --write is explicit.  The
migration preserves canonical IDs, moves external URLs out of related_raw,
builds resolvable authority IDs and typed compatibility relations, and leaves
claim-level evidence empty for human verification rather than fabricating it.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from graph_contract import RELATED_FIELDS
from kg_common import (
    SCHEMA_VERSION,
    URL_RE,
    as_list,
    dump_subset_yaml,
    entity_lookup,
    load_entities,
    load_json,
    normalized_ref,
    parse_date,
    resolve_entity_ref,
    scalar_text,
    wiki_targets,
    write_json,
)
from review_policy import recommended_review_cycle as _recommended_cycle
from source_catalog import iter_raw_files


COMMON_ORDER = (
    "schema_version", "id", "id_aliases", "entity_type", "title", "aliases", "jurisdiction",
    "status", "legal_status", "ingestion_status", "primary_authority", "primary_authority_id",
    "authority_ids", "authority_level", "enforcement_weight", "conflict_status", "conflict_type",
    "conflict_resolution", "conflict_resolution_note", "conflict_resolved_date", "effective_from",
    "effective_to", "as_of_date", "superseded_by", "superseded_date", "review_cycle", "review_trigger",
    "related_concepts", "related_rules", "related_cases", "related_laws", "related_interpretations",
    "related_fact_patterns", "related_raw", "source_urls", "source_excerpt", "evidence", "relations",
    "last_checked", "last_verified", "last_updated", "verified_by",
)
TYPE_ORDER = {
    "case": ("court_name", "case_number", "case_numbers", "decision_date", "case_role", "holding_summary", "legal_principles", "source_availability", "source_availability_note"),
    "rule": ("rule_type", "issue", "elements", "exceptions", "conclusion", "temporal", "law_version", "law_revision_date", "wage_criteria", "decision_factors", "wage_type", "worker_scope", "calculation_unit", "extinction_period"),
    "law": ("law_version", "law_revision_date", "promulgation_date", "enforcement_date"),
    "interpretation": ("issuing_agency", "document_number", "issue_date", "interpretation_type", "legal_effect"),
}


def _ordered(data: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in COMMON_ORDER + TYPE_ORDER.get(scalar_text(data.get("entity_type")), ()):
        if key in data and key not in result:
            result[key] = data[key]
    for key, value in data.items():
        if key not in result:
            result[key] = value
    return result


def _infer_legal_status(data: dict[str, Any], as_of: dt.date) -> str:
    old_status = scalar_text(data.get("status"))
    if scalar_text(data.get("conflict_type")) == "overruled":
        return "overruled"
    if old_status == "legacy":
        return "superseded" if scalar_text(data.get("superseded_by")) else "historical"
    if scalar_text(data.get("superseded_by")):
        return "superseded"
    start = parse_date(data.get("effective_from"))
    end = parse_date(data.get("effective_to"))
    if start and start > as_of:
        return "future"
    if end and end < as_of:
        return "historical"
    return "current"


def _source_urls(data: dict[str, Any]) -> tuple[list[str], list[Any]]:
    urls = [scalar_text(item) for item in as_list(data.get("source_urls")) if scalar_text(item)]
    retained: list[Any] = []
    for item in as_list(data.get("related_raw")):
        text = scalar_text(item)
        if URL_RE.match(text):
            urls.append(text)
        else:
            retained.append(item)
    return list(dict.fromkeys(urls)), retained


def _raw_names(root: Path) -> set[str]:
    result: set[str] = set()
    for path in iter_raw_files(root, include_hidden=True, include_control_files=True):
        relative = path.relative_to(root).as_posix()
        result.update({normalized_ref(relative), normalized_ref(path.name), normalized_ref(path.stem)})
    return result


def _has_own_case_raw(data: dict[str, Any], raw_names: set[str]) -> bool:
    case_number = re.sub(r"\s+", "", scalar_text(data.get("case_number"))).casefold()
    if not case_number:
        return False
    for target in wiki_targets(data.get("related_raw")):
        normalized = normalized_ref(target)
        compact = re.sub(r"\s+", "", normalized)
        exists = normalized in raw_names or normalized_ref(Path(normalized).name) in raw_names
        if exists and case_number in compact:
            return True
    return False


def _resolve_related(entity: Any, names: dict[str, list[Any]]) -> list[Any]:
    result: list[Any] = []
    for field in ("related_cases", "related_laws", "related_interpretations"):
        for target in wiki_targets(entity.data.get(field)):
            for match in resolve_entity_ref(target, names):
                if match not in result:
                    result.append(match)
    return result


def _authority_ids(entity: Any, names: dict[str, list[Any]]) -> tuple[str, list[str], bool]:
    entity_id = scalar_text(entity.data.get("id"))
    entity_type = scalar_text(entity.data.get("entity_type"))
    existing_primary = scalar_text(entity.data.get("primary_authority_id"))
    existing_authorities = [
        scalar_text(item) for item in as_list(entity.data.get("authority_ids")) if scalar_text(item)
    ]
    if existing_primary or existing_authorities:
        return existing_primary, list(dict.fromkeys(existing_authorities)), True
    if entity_type in {"case", "law", "interpretation"} and entity_id:
        return entity_id, [entity_id], True
    targets = _resolve_related(entity, names)
    target_ids = [scalar_text(target.data.get("id")) for target in targets if scalar_text(target.data.get("id"))]
    primary_text = re.sub(r"\s+", "", scalar_text(entity.data.get("primary_authority"))).casefold()
    exact: list[str] = []
    for target in targets:
        target_id = scalar_text(target.data.get("id"))
        needles = (
            scalar_text(target.data.get("case_number")),
            scalar_text(target.data.get("document_number")),
            scalar_text(target.data.get("title")),
        )
        if target_id and any(re.sub(r"\s+", "", needle).casefold() in primary_text for needle in needles if needle):
            exact.append(target_id)
    primary = exact[0] if exact else (target_ids[0] if not primary_text and len(target_ids) == 1 else "")
    return primary, list(dict.fromkeys(target_ids)), bool(primary or not primary_text)


def _relation_type(source_type: str, target_type: str) -> str:
    if source_type == "case" and target_type == "rule":
        return "supports"
    if source_type == "law" and target_type == "rule":
        return "establishes"
    if source_type == "interpretation" and target_type == "rule":
        return "interprets"
    if source_type == "fact_pattern" and target_type == "rule":
        return "applies"
    if source_type == "rule" and target_type == "fact_pattern":
        return "illustrated_by"
    return "cites"


def _relations(entity: Any, names: dict[str, list[Any]]) -> tuple[list[dict[str, str]], list[str]]:
    existing = entity.data.get("relations")
    if isinstance(existing, list) and existing:
        return existing, []
    result: list[dict[str, str]] = []
    unresolved: list[str] = []
    seen: set[tuple[str, str]] = set()
    source_type = scalar_text(entity.data.get("entity_type"))
    for field in RELATED_FIELDS:
        for target in wiki_targets(entity.data.get(field)):
            matches = resolve_entity_ref(target, names)
            if len(matches) != 1:
                unresolved.append(target)
                continue
            match = matches[0]
            target_id = scalar_text(match.data.get("id"))
            relation_type = _relation_type(source_type, scalar_text(match.data.get("entity_type")))
            pair = (relation_type, target_id)
            if target_id and pair not in seen:
                result.append({"relation_type": relation_type, "target_id": target_id, "target": f"[[{match.path.stem}]]", "note": "v1.2 related_* 링크에서 이관"})
                seen.add(pair)
    return result, unresolved


def _migrate_entity(
    entity: Any,
    root: Path,
    names: dict[str, list[Any]],
    alias_map: dict[str, str],
    wage_criteria_vocab: set[str],
    as_of: dt.date,
    raw_names: set[str],
    unavailable_case_ids: set[str],
    apply_review_policy: bool,
    verified_by: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    data = dict(entity.data)
    changed_fields: list[str] = []

    def set_default(key: str, value: Any) -> None:
        if key not in data:
            data[key] = value
            changed_fields.append(key)

    was_v13 = scalar_text(entity.data.get("schema_version")) == SCHEMA_VERSION
    old_status = scalar_text(data.get("status"))
    if old_status == "legacy":
        data["status"] = "verified" if scalar_text(data.get("last_verified")) else "review"
        changed_fields.append("status")
    if not was_v13 and data.get("status") == "verified":
        if not verified_by:
            data["status"] = "review"
            changed_fields.append("status")
        else:
            data["ingestion_status"] = "verified"
            data["last_verified"] = as_of.isoformat()
            data["last_checked"] = as_of.isoformat()
            data["verified_by"] = [verified_by]
            changed_fields.extend(["ingestion_status", "last_verified", "last_checked", "verified_by"])
    data["schema_version"] = SCHEMA_VERSION
    if scalar_text(entity.data.get("schema_version")) != SCHEMA_VERSION:
        changed_fields.append("schema_version")
    set_default("jurisdiction", "KR")
    set_default("legal_status", _infer_legal_status(data, as_of))
    set_default("as_of_date", as_of.isoformat())
    set_default("last_checked", as_of.isoformat())
    set_default("verified_by", [verified_by] if verified_by and data.get("status") == "verified" else [])
    set_default("aliases", [])
    entity_id = scalar_text(data.get("id"))
    corrected_aliases = [alias for alias, canonical in alias_map.items() if canonical == entity_id]
    if "id_aliases" not in data:
        data["id_aliases"] = corrected_aliases
        changed_fields.append("id_aliases")
    else:
        merged_aliases = list(dict.fromkeys([scalar_text(item) for item in as_list(data.get("id_aliases"))] + corrected_aliases))
        if merged_aliases != data.get("id_aliases"):
            data["id_aliases"] = merged_aliases
            changed_fields.append("id_aliases")
    primary_id, authority_ids, authority_resolved = _authority_ids(entity, names)
    set_default("primary_authority_id", primary_id)
    set_default("authority_ids", authority_ids)
    urls, retained_raw = _source_urls(data)
    if "source_urls" not in data:
        data["source_urls"] = urls
        changed_fields.append("source_urls")
    elif urls != as_list(data.get("source_urls")):
        data["source_urls"] = urls
        changed_fields.append("source_urls")
    if retained_raw != as_list(data.get("related_raw")):
        data["related_raw"] = retained_raw
        changed_fields.append("related_raw")
    set_default("evidence", [])
    relations, unresolved_relations = _relations(entity, names)
    set_default("relations", relations)
    set_default("related_interpretations", [])
    old_conflict_status = scalar_text(data.get("conflict_status"))
    old_conflict_type = scalar_text(data.get("conflict_type"))
    old_resolution = scalar_text(data.get("conflict_resolution"))
    if old_conflict_status == "resolved":
        data["conflict_status"] = "active"
        data["conflict_resolution"] = "resolved"
        if old_resolution and old_resolution not in {"pending", "resolved", "unresolvable"} and not scalar_text(data.get("conflict_resolution_note")):
            data["conflict_resolution_note"] = old_resolution
        if not scalar_text(data.get("conflict_resolved_date")) and scalar_text(data.get("superseded_date")):
            data["conflict_resolved_date"] = scalar_text(data.get("superseded_date"))
        changed_fields.extend(["conflict_status", "conflict_resolution", "conflict_resolution_note", "conflict_resolved_date"])
    if old_conflict_type == "overruled":
        data["conflict_type"] = "temporal"
        changed_fields.append("conflict_type")
    recommended_cycle = _recommended_cycle(
        scalar_text(data.get("entity_type")), scalar_text(data.get("title")), data, as_of
    )
    existing_cycle = scalar_text(data.get("review_cycle"))
    if not existing_cycle:
        data["review_cycle"] = recommended_cycle
        changed_fields.append("review_cycle")
    elif apply_review_policy and existing_cycle != recommended_cycle:
        data["review_cycle"] = recommended_cycle
        changed_fields.append("review_cycle")

    entity_type = scalar_text(data.get("entity_type"))
    if entity_type == "case":
        if scalar_text(data.get("case_role")) == "legacy":
            data["case_role"] = "conflicting"
            changed_fields.append("case_role")
        own_raw = _has_own_case_raw(data, raw_names)
        if entity_id in unavailable_case_ids:
            availability = "unavailable_official"
            note = f"{as_of.isoformat()} 공식 판례 검색 결과를 source_urls에 기록했으나 판결문 원문은 공개 확인되지 않음"
        elif own_raw:
            availability, note = "available", ""
        else:
            availability = "partial"
            note = "자체 판결 원문 미보유: 공식 원문 공개 여부와 검색 근거를 추가 확인해야 함"
        set_default("source_availability", availability)
        set_default("source_availability_note", note)
    elif entity_type == "rule":
        set_default("issue", "")
        set_default("elements", [])
        set_default("exceptions", [])
        set_default("conclusion", "")
        set_default("temporal", {
            "applicable_from": scalar_text(data.get("effective_from")) or "1900-01-01",
            "applicable_to": scalar_text(data.get("effective_to")) or "9999-12-31",
            "rule_version": scalar_text(data.get("law_version")),
            "transition_note": "",
        })
        criteria = [scalar_text(item) for item in as_list(data.get("wage_criteria")) if scalar_text(item)]
        controlled = [item for item in criteria if item in wage_criteria_vocab]
        free_form = [item for item in criteria if item not in wage_criteria_vocab]
        if controlled != criteria:
            data["wage_criteria"] = controlled
            changed_fields.append("wage_criteria")
        set_default("decision_factors", free_form)

    report = {
        "path": entity.relative_path,
        "id": entity_id,
        "changed_fields": sorted(set(changed_fields)),
        "authority_resolved": authority_resolved,
        "unresolved_authority": scalar_text(data.get("primary_authority")) if not authority_resolved else "",
        "unresolved_relation_targets": sorted(set(unresolved_relations)),
        "review_cycle_existing": existing_cycle,
        "review_cycle_recommended": recommended_cycle,
        "review_cycle_will_change": bool(apply_review_policy and existing_cycle and existing_cycle != recommended_cycle),
        "evidence_requires_review": entity_type in {"rule", "case", "law", "interpretation"} and not as_list(data.get("evidence")),
        "manual_review_fields": (
            [field for field in ("issue", "elements", "conclusion", "law_version", "extinction_period", "temporal.rule_version")
             if (not as_list(data.get(field)) if field == "elements" else
                 not scalar_text(data.get("temporal", {}).get("rule_version")) if field == "temporal.rule_version" and isinstance(data.get("temporal"), dict) else
                 not scalar_text(data.get(field)))]
            if entity_type == "rule" else []
        ),
    }
    return _ordered(data), report


def _render_document(data: dict[str, Any], body: str) -> str:
    return "---\n" + dump_subset_yaml(data) + "---\n" + body.lstrip("\r\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, help="write migration JSON report; stdout when omitted")
    parser.add_argument("--as-of-date", type=dt.date.fromisoformat, default=dt.date.today())
    parser.add_argument("--write", action="store_true", help="apply changes; default is dry-run")
    parser.add_argument("--apply-review-policy", action="store_true", help="replace explicit review_cycle values with the v1.3 policy")
    parser.add_argument("--unavailable-case-id", action="append", default=[], help="case ID whose official full text is confirmed unavailable; repeatable")
    parser.add_argument("--verified-by", default="", help="verifier ID to retain verified status when verification was performed in this migration review")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    entities, parse_issues = load_entities(root)
    _, names = entity_lookup(entities)
    vocab = load_json(root / "schemas" / "vocabularies.json", {})
    aliases = load_json(root / "schemas" / "id-aliases.json", {}).get("aliases_to_canonical", {})
    raw_names = _raw_names(root)
    file_reports: list[dict[str, Any]] = []
    changed = 0
    for entity in entities:
        migrated, file_report = _migrate_entity(
            entity, root, names, aliases, set(vocab.get("wage_criteria", [])), args.as_of_date,
            raw_names, set(args.unavailable_case_id), args.apply_review_policy,
            args.verified_by,
        )
        rendered = _render_document(migrated, entity.body)
        original = entity.path.read_text(encoding="utf-8-sig")
        differs = original.lstrip("\ufeff").replace("\r\n", "\n") != rendered.replace("\r\n", "\n")
        file_report["would_change"] = differs
        file_reports.append(file_report)
        if differs:
            changed += 1
            if args.write:
                entity.path.write_text(rendered, encoding="utf-8", newline="\n")
    report = {
        "schema_version": SCHEMA_VERSION,
        "mode": "write" if args.write else "dry-run",
        "as_of_date": args.as_of_date.isoformat(),
        "root": root.as_posix(),
        "summary": {
            "entities": len(entities),
            "files_changed": changed if args.write else 0,
            "files_would_change": changed,
            "parse_issues": len(parse_issues),
            "unresolved_authorities": sum(bool(item["unresolved_authority"]) for item in file_reports),
            "evidence_review_required": sum(bool(item["evidence_requires_review"]) for item in file_reports),
            "review_cycle_proposals": sum(item["review_cycle_existing"] != item["review_cycle_recommended"] for item in file_reports),
            "manual_rule_field_reviews": sum(bool(item["manual_review_fields"]) for item in file_reports),
        },
        "parse_issues": parse_issues,
        "files": file_reports,
    }
    write_json(report, args.output)
    return 1 if parse_issues else 0


if __name__ == "__main__":
    sys.exit(main())
