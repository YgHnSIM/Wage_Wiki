#!/usr/bin/env python3
"""Export entity, authority, evidence, and typed-relation graph data as JSON."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from graph_contract import RELATED_FIELD_TYPES
from kg_common import (
    SCHEMA_VERSION,
    as_list,
    entity_lookup,
    load_entities,
    load_json,
    load_registry_ids,
    resolve_entity_ref,
    scalar_text,
    wiki_targets,
    write_json,
)


RELATED_FIELDS = RELATED_FIELD_TYPES


def _edge_id(source: str, relation: str, target: str) -> str:
    digest = hashlib.sha256(f"{source}\0{relation}\0{target}".encode("utf-8")).hexdigest()[:16]
    return f"edge-{digest}"


def export_graph(root: Path) -> dict[str, Any]:
    root = root.resolve()
    entities, parse_issues = load_entities(root)
    by_id, names = entity_lookup(entities)
    global_aliases = load_json(root / "schemas" / "id-aliases.json", {}).get("aliases_to_canonical", {})
    aliases_by_canonical: dict[str, list[str]] = {}
    if isinstance(global_aliases, dict):
        for alias, canonical in global_aliases.items():
            aliases_by_canonical.setdefault(str(canonical), []).append(str(alias))
    nodes: list[dict[str, Any]] = []
    for entity in entities:
        data = entity.data
        nodes.append({
            "id": scalar_text(data.get("id")),
            "node_type": scalar_text(data.get("entity_type")),
            "title": scalar_text(data.get("title")),
            "aliases": as_list(data.get("aliases")),
            "id_aliases": list(dict.fromkeys(as_list(data.get("id_aliases")) + aliases_by_canonical.get(scalar_text(data.get("id")), []))),
            "path": entity.relative_path,
            "status": scalar_text(data.get("status")),
            "legal_status": scalar_text(data.get("legal_status")),
            "jurisdiction": scalar_text(data.get("jurisdiction")) or "KR",
            "authority_level": data.get("authority_level"),
            "effective_from": scalar_text(data.get("effective_from")),
            "effective_to": scalar_text(data.get("effective_to")),
            "as_of_date": scalar_text(data.get("as_of_date")),
        })
    source_ids = load_registry_ids(root)
    for source_id in sorted(source_ids):
        nodes.append({"id": source_id, "node_type": "source", "title": source_id})

    edges_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}

    def add_edge(source: str, relation: str, target: str, origin: str, note: str = "") -> None:
        if not source or not target:
            return
        key = (source, relation, target)
        record = edges_by_key.setdefault(key, {
            "id": _edge_id(source, relation, target),
            "source": source,
            "relation_type": relation,
            "target": target,
            "origins": [],
            "notes": [],
        })
        if origin not in record["origins"]:
            record["origins"].append(origin)
        if note and note not in record["notes"]:
            record["notes"].append(note)

    for entity in entities:
        data = entity.data
        source_id = scalar_text(data.get("id"))
        for relation in as_list(data.get("relations")):
            if isinstance(relation, dict):
                add_edge(source_id, scalar_text(relation.get("relation_type")), scalar_text(relation.get("target_id")), "relations", scalar_text(relation.get("note")))
        for field in RELATED_FIELDS:
            for target in wiki_targets(data.get(field)):
                matches = resolve_entity_ref(target, names)
                if len(matches) == 1:
                    add_edge(source_id, "related_to", scalar_text(matches[0].data.get("id")), field)
        primary = scalar_text(data.get("primary_authority_id"))
        if primary:
            add_edge(source_id, "has_primary_authority", primary, "primary_authority_id")
        for authority_id in as_list(data.get("authority_ids")):
            add_edge(source_id, "has_authority", scalar_text(authority_id), "authority_ids")
        for evidence in as_list(data.get("evidence")):
            if isinstance(evidence, dict):
                add_edge(source_id, "supported_by", scalar_text(evidence.get("source_id")), "evidence", scalar_text(evidence.get("locator")))
    edges = sorted(edges_by_key.values(), key=lambda item: (item["source"], item["relation_type"], item["target"]))
    nodes.sort(key=lambda item: (item.get("node_type", ""), item.get("id", "")))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "root": root.as_posix(),
        "stats": {"nodes": len(nodes), "edges": len(edges), "parse_issues": len(parse_issues)},
        "parse_issues": parse_issues,
        "nodes": nodes,
        "edges": edges,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, help="write JSON here; stdout when omitted")
    args = parser.parse_args(argv)
    report = export_graph(args.root)
    write_json(report, args.output)
    return 1 if report["parse_issues"] else 0


if __name__ == "__main__":
    sys.exit(main())
