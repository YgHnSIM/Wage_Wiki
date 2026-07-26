#!/usr/bin/env python3
"""Normalize ``sources/registry.yaml`` to the v1.1 location contract."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import Any

from kg_common import _SubsetYamlParser, dump_subset_yaml, scalar_text, write_json


def normalize(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    path = root / "sources" / "registry.yaml"
    data = _SubsetYamlParser(path.read_text(encoding="utf-8-sig")).parse()
    records = data.get("sources") if isinstance(data, dict) else None
    if not isinstance(records, list):
        raise ValueError("sources must be a list")
    output_records: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("source record must be a mapping")
        location = record.get("location")
        if not isinstance(location, dict):
            path_value = scalar_text(record.get("path"))
            url_value = scalar_text(record.get("url") or record.get("base_url"))
            if path_value:
                location = {"kind": "path", "path": path_value}
            elif url_value:
                location = {"kind": "url", "url": url_value}
            else:
                raise ValueError(f"source has no location: {record.get('source_id')}")
        normalized = {
            "source_id": scalar_text(record.get("source_id")),
            "title": scalar_text(record.get("title")),
            "publisher": scalar_text(record.get("publisher")),
            "source_type": scalar_text(record.get("source_type")),
            "jurisdiction": scalar_text(record.get("jurisdiction")) or "KR",
            "authority_level": record.get("authority_level"),
            "location": location,
        }
        output_records.append(normalized)
    normalized_root = {
        "format_version": "1.1",
        "last_updated": scalar_text(data.get("last_updated")) or dt.date.today().isoformat(),
        "id_policy": scalar_text(data.get("id_policy")) or "raw-<source_type>-<stable-number-or-slug>",
        "sources": output_records,
    }
    report = {
        "schema_version": "1.1",
        "source_count": len(output_records),
        "path_locations": sum(item["location"].get("kind") == "path" for item in output_records),
        "url_locations": sum(item["location"].get("kind") == "url" for item in output_records),
    }
    return normalized_root, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    normalized, report = normalize(root)
    report["mode"] = "write" if args.write else "dry-run"
    registry_path = root / "sources" / "registry.yaml"
    original = registry_path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    rendered = dump_subset_yaml(normalized).replace("\r\n", "\n")
    report["would_change"] = original != rendered
    if args.write:
        temp = registry_path.with_name(".registry.yaml.v11.tmp")
        temp.write_text(dump_subset_yaml(normalized), encoding="utf-8", newline="\n")
        temp.replace(registry_path)
    write_json(report, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
