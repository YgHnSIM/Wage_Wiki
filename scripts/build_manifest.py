#!/usr/bin/env python3
"""Build or verify a deterministic SHA-256 manifest for immutable raw sources."""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from pathlib import Path
from typing import Any

from kg_common import FrontmatterError, _SubsetYamlParser, normalized_ref, scalar_text, sha256_file


def _registry_paths(root: Path) -> dict[str, str]:
    path = root / "sources" / "registry.yaml"
    if not path.exists():
        return {}
    try:
        data = _SubsetYamlParser(path.read_text(encoding="utf-8-sig")).parse()
    except (OSError, UnicodeError, FrontmatterError):
        return {}
    result: dict[str, str] = {}
    sources = data.get("sources", [])
    if not isinstance(sources, list):
        return result
    for record in sources:
        if not isinstance(record, dict):
            continue
        source_id = scalar_text(record.get("source_id"))
        source_path = scalar_text(record.get("path"))
        if source_id and source_path:
            result[normalized_ref(source_path)] = source_id
    return result


TEMP_NAMES = {".gitkeep", ".ds_store", "thumbs.db"}
TEMP_SUFFIXES = {".tmp", ".part", ".crdownload"}


def _is_control_or_temporary(path: Path, raw_root: Path, include_hidden: bool) -> bool:
    relative_parts = path.relative_to(raw_root).parts
    if path.name.casefold() in TEMP_NAMES or path.suffix.casefold() in TEMP_SUFFIXES or path.name.startswith("~$"):
        return True
    return not include_hidden and any(part.startswith(".") for part in relative_parts)


def build_manifest(root: Path, include_hidden: bool = False) -> list[dict[str, Any]]:
    root = root.resolve()
    raw_root = root / "raw"
    registry = _registry_paths(root)
    records: list[dict[str, Any]] = []
    if not raw_root.exists():
        return records
    for path in sorted((item for item in raw_root.rglob("*") if item.is_file()), key=lambda item: item.as_posix().casefold()):
        if _is_control_or_temporary(path, raw_root, include_hidden):
            continue
        relative = path.relative_to(root).as_posix()
        digest = sha256_file(path)
        category = path.relative_to(raw_root).parts[0] if len(path.relative_to(raw_root).parts) > 1 else "_root"
        records.append({
            "source_id": registry.get(normalized_ref(relative), f"raw-sha256-{digest[:16]}"),
            "path": relative,
            "category": category,
            "media_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            "size_bytes": path.stat().st_size,
            "sha256": digest,
        })
    return records


def render_jsonl(records: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, help="write JSONL here; stdout when omitted")
    parser.add_argument("--check", type=Path, help="compare generated data with an existing JSONL file")
    parser.add_argument("--include-hidden", action="store_true", help="include hidden raw files; control placeholders and temporary downloads remain excluded")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    rendered = render_jsonl(build_manifest(args.root, include_hidden=args.include_hidden))
    if args.check:
        try:
            existing = args.check.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        except OSError as exc:
            print(f"manifest check failed: {exc}", file=sys.stderr)
            return 1
        if existing != rendered:
            print(f"manifest is stale: {args.check}", file=sys.stderr)
            return 1
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    elif not args.check:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
