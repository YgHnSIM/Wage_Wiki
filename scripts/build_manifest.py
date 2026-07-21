#!/usr/bin/env python3
"""Build or verify a deterministic SHA-256 manifest for immutable raw sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import sys
from pathlib import Path
from typing import Any

from kg_common import normalized_ref, sha256_file
from source_catalog import (
    TEMP_NAMES,
    TEMP_SUFFIXES,
    is_control_or_temporary,
    iter_raw_files,
    registry_path_map,
)


LF_NORMALIZED_SUFFIXES = frozenset({
    ".css",
    ".html",
    ".js",
    ".json",
    ".jsonl",
    ".md",
    ".py",
    ".svg",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
})


def _registry_paths(root: Path) -> dict[str, str]:
    return registry_path_map(root)


def _is_control_or_temporary(path: Path, raw_root: Path, include_hidden: bool) -> bool:
    return is_control_or_temporary(path, raw_root, include_hidden=include_hidden)


def _manifest_digest_and_size(path: Path) -> tuple[str, int]:
    """Hash the canonical Git representation of a raw source.

    Text formats covered by ``.gitattributes`` are committed with LF endings.
    Normalizing CRLF here keeps manifests identical when a Windows working tree
    still contains CRLF or mixed endings before Git writes the index.
    """

    if path.suffix.casefold() not in LF_NORMALIZED_SUFFIXES:
        return sha256_file(path), path.stat().st_size

    digest = hashlib.sha256()
    size = 0
    pending_cr = b""
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            chunk = pending_cr + chunk
            if chunk.endswith(b"\r"):
                pending_cr = b"\r"
                chunk = chunk[:-1]
            else:
                pending_cr = b""
            canonical = chunk.replace(b"\r\n", b"\n")
            digest.update(canonical)
            size += len(canonical)
    if pending_cr:
        digest.update(pending_cr)
        size += 1
    return digest.hexdigest(), size


def build_manifest(root: Path, include_hidden: bool = False) -> list[dict[str, Any]]:
    root = root.resolve()
    raw_root = root / "raw"
    registry = _registry_paths(root)
    records: list[dict[str, Any]] = []
    for path in iter_raw_files(root, include_hidden=include_hidden):
        relative = path.relative_to(root).as_posix()
        digest, size = _manifest_digest_and_size(path)
        category = path.relative_to(raw_root).parts[0] if len(path.relative_to(raw_root).parts) > 1 else "_root"
        records.append({
            "source_id": registry.get(normalized_ref(relative), f"raw-sha256-{digest[:16]}"),
            "path": relative,
            "category": category,
            "media_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            "size_bytes": size,
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
