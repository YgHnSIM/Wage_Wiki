#!/usr/bin/env python3
"""Export entity, authority, evidence, and typed-relation graph data as JSON."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from claim_contract import (
    claim_anchors,
    evidence_claim_ids,
    global_claim_id,
    global_evidence_id,
    global_source_id,
    resolved_claim_ids,
)
from graph_contract import RELATED_FIELD_TYPES
from kg_common import (
    SCHEMA_VERSION,
    as_list,
    entity_lookup,
    issue,
    load_entities,
    load_json,
    resolve_entity_ref,
    scalar_text,
    wiki_targets,
    write_json,
)
from source_catalog import known_source_ids


RELATED_FIELDS = RELATED_FIELD_TYPES
GRAPH_SCHEMA_VERSION = "2.0"


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
        entity_id = scalar_text(data.get("id"))
        nodes.append({
            "id": entity_id,
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
        resolved_anchors = resolved_claim_ids(data, entity.body)
        for claim_id in evidence_claim_ids(data.get("evidence")):
            nodes.append({
                "id": global_claim_id(entity_id, claim_id),
                "node_type": "claim",
                "title": claim_id,
                "owner_id": entity_id,
                "claim_id": claim_id,
                "anchor_resolved": claim_id in resolved_anchors,
            })
    source_ids = known_source_ids(root)
    for source_id in sorted(source_ids):
        nodes.append({"id": global_source_id(source_id), "node_type": "source", "title": source_id})

    edges_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    graph_input_issues: list[dict[str, Any]] = []

    def canonical_entity_id(reference: str) -> str:
        matches = resolve_entity_ref(reference, names)
        if len(matches) == 1:
            return scalar_text(matches[0].data.get("id"))
        return reference

    def add_edge(
        source: str,
        relation: str,
        target: str,
        origin: str,
        note: str = "",
        *,
        evidence_ref: str = "",
        claim_ref: str = "",
    ) -> None:
        if not source or not target:
            graph_input_issues.append(
                issue(
                    "critical",
                    "GRAPH_EDGE_ENDPOINT_EMPTY",
                    origin,
                    f"graph edge has an empty {'source' if not source else 'target'} endpoint",
                    "source" if not source else "target",
                )
            )
            return
        key = (source, relation, target)
        record = edges_by_key.setdefault(key, {
            "id": _edge_id(source, relation, target),
            "source": source,
            "relation_type": relation,
            "target": target,
            "origins": [],
            "notes": [],
            "evidence_refs": [],
            "claim_refs": [],
            "evidence_links": [],
        })
        if origin not in record["origins"]:
            record["origins"].append(origin)
        if note and note not in record["notes"]:
            record["notes"].append(note)
        if evidence_ref and evidence_ref not in record["evidence_refs"]:
            record["evidence_refs"].append(evidence_ref)
        if claim_ref and claim_ref not in record["claim_refs"]:
            record["claim_refs"].append(claim_ref)
        if evidence_ref:
            evidence_link = {
                "evidence_ref": evidence_ref,
                "locator": note,
                "claim_ref": claim_ref,
            }
            if evidence_link not in record["evidence_links"]:
                record["evidence_links"].append(evidence_link)

    for entity in entities:
        data = entity.data
        source_id = scalar_text(data.get("id"))
        for relation in as_list(data.get("relations")):
            if isinstance(relation, dict):
                target_id = canonical_entity_id(scalar_text(relation.get("target_id")))
                add_edge(source_id, scalar_text(relation.get("relation_type")), target_id, "relations", scalar_text(relation.get("note")))
        for field in RELATED_FIELDS:
            for target in wiki_targets(data.get(field)):
                matches = resolve_entity_ref(target, names)
                if len(matches) == 1:
                    add_edge(source_id, "related_to", scalar_text(matches[0].data.get("id")), field)
        primary = scalar_text(data.get("primary_authority_id"))
        if primary:
            add_edge(source_id, "has_primary_authority", canonical_entity_id(primary), "primary_authority_id")
        for authority_id in as_list(data.get("authority_ids")):
            add_edge(source_id, "has_authority", canonical_entity_id(scalar_text(authority_id)), "authority_ids")
        for evidence in as_list(data.get("evidence")):
            if isinstance(evidence, dict):
                evidence_id = scalar_text(evidence.get("evidence_id"))
                evidence_source = scalar_text(evidence.get("source_id"))
                source_ref = global_source_id(evidence_source)
                evidence_ref = global_evidence_id(source_id, evidence_id)
                locator = scalar_text(evidence.get("locator"))
                claim_refs = [
                    global_claim_id(source_id, scalar_text(raw))
                    for raw in as_list(evidence.get("supports"))
                    if scalar_text(raw)
                ]
                for claim_ref in claim_refs:
                    add_edge(
                        source_id,
                        "asserts",
                        claim_ref,
                        "evidence",
                        evidence_ref=evidence_ref,
                        claim_ref=claim_ref,
                    )
                    add_edge(
                        claim_ref,
                        "supported_by",
                        source_ref,
                        "evidence",
                        locator,
                        evidence_ref=evidence_ref,
                        claim_ref=claim_ref,
                    )
                if claim_refs:
                    for claim_ref in claim_refs:
                        add_edge(
                            source_id,
                            "supported_by",
                            source_ref,
                            "evidence",
                            locator,
                            evidence_ref=evidence_ref,
                            claim_ref=claim_ref,
                        )
                else:
                    add_edge(
                        source_id,
                        "supported_by",
                        source_ref,
                        "evidence",
                        locator,
                        evidence_ref=evidence_ref,
                    )
    edges = sorted(edges_by_key.values(), key=lambda item: (item["source"], item["relation_type"], item["target"]))
    nodes.sort(key=lambda item: (item.get("node_type", ""), item.get("id", "")))
    graph_issues = list(parse_issues) + graph_input_issues
    node_counts = Counter(str(node.get("id", "")) for node in nodes)
    for node_id, count in sorted(node_counts.items()):
        if not node_id:
            graph_issues.append(
                issue(
                    "critical",
                    "GRAPH_NODE_ID_MISSING",
                    "build/graph.json",
                    "graph node ID is empty",
                    "nodes",
                )
            )
            continue
        if count < 2:
            continue
        graph_issues.append(
            issue(
                "critical",
                "GRAPH_NODE_ID_DUPLICATE",
                "build/graph.json",
                f"graph node ID is duplicated {count} times: {node_id}",
                "nodes",
            )
        )
    node_ids = set(node_counts)
    for edge in edges:
        if not edge["relation_type"]:
            graph_issues.append(
                issue(
                    "critical",
                    "GRAPH_EDGE_RELATION_MISSING",
                    "build/graph.json",
                    f"edge {edge['id']} has no relation_type",
                    "edges.relation_type",
                )
            )
        for endpoint in ("source", "target"):
            if edge[endpoint] not in node_ids:
                graph_issues.append(
                    issue(
                        "critical",
                        "GRAPH_EDGE_ENDPOINT_MISSING",
                        "build/graph.json",
                        f"edge {edge['id']} has no {endpoint} node: {edge[endpoint]}",
                        f"edges.{endpoint}",
                    )
                )
    return {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "entity_schema_version": SCHEMA_VERSION,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "root": root.as_posix(),
        "stats": {"nodes": len(nodes), "edges": len(edges), "parse_issues": len(graph_issues)},
        "parse_issues": graph_issues,
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
