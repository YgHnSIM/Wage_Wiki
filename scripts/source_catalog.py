#!/usr/bin/env python3
"""Shared source-registry access and raw-file enumeration policy."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from kg_common import FrontmatterError, _SubsetYamlParser, normalized_ref, scalar_text


TEMP_NAMES = frozenset({".gitkeep", ".ds_store", "thumbs.db"})
TEMP_SUFFIXES = frozenset({".tmp", ".part", ".crdownload"})


class SourceRegistryError(ValueError):
    """A typed source-registry loading failure."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


def load_source_records(root: Path, *, missing_ok: bool = False) -> list[Any]:
    """Load raw registry records, preserving invalid items for strict validators."""

    path = root / "sources" / "registry.yaml"
    if not path.exists():
        if missing_ok:
            return []
        raise SourceRegistryError("missing", "source registry does not exist")
    try:
        data = _SubsetYamlParser(path.read_text(encoding="utf-8-sig")).parse()
    except (OSError, UnicodeError, FrontmatterError) as exc:
        raise SourceRegistryError("parse", str(exc)) from exc
    records = data.get("sources")
    if not isinstance(records, list):
        raise SourceRegistryError("type", "sources must be a list")
    return records


def tolerant_source_records(root: Path) -> list[dict[str, Any]]:
    """Return valid mapping records, silently falling back for generation tools."""

    try:
        records = load_source_records(root, missing_ok=True)
    except SourceRegistryError:
        return []
    return [record for record in records if isinstance(record, dict)]


def registry_ids(root: Path) -> set[str]:
    return {
        source_id
        for record in tolerant_source_records(root)
        if (source_id := scalar_text(record.get("source_id")))
    }


def manifest_ids(root: Path) -> set[str]:
    """Return valid source IDs from the generated manifest without raising."""

    path = root / "sources" / "raw-manifest.jsonl"
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError):
        return set()
    result: set[str] = set()
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and (source_id := scalar_text(record.get("source_id"))):
            result.add(source_id)
    return result


def known_source_ids(root: Path) -> set[str]:
    """Unify registry and manifest source identity for read-only generators."""

    return registry_ids(root) | manifest_ids(root)


def registry_path_map(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for record in tolerant_source_records(root):
        source_id = scalar_text(record.get("source_id"))
        source_path = scalar_text(record.get("path"))
        if source_id and source_path:
            result[normalized_ref(source_path)] = source_id
    return result


def registry_title_map(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for record in tolerant_source_records(root):
        source_id = scalar_text(record.get("source_id"))
        title = scalar_text(record.get("title"))
        if source_id and title:
            result[source_id] = title
    return result


def is_control_or_temporary(path: Path, raw_root: Path, *, include_hidden: bool) -> bool:
    relative_parts = path.relative_to(raw_root).parts
    if (
        path.name.casefold() in TEMP_NAMES
        or path.suffix.casefold() in TEMP_SUFFIXES
        or path.name.startswith("~$")
    ):
        return True
    return not include_hidden and any(part.startswith(".") for part in relative_parts)


def iter_raw_files(
    root: Path,
    *,
    include_hidden: bool = False,
    include_control_files: bool = False,
) -> Iterator[Path]:
    """Yield raw files deterministically under an explicit inclusion policy."""

    raw_root = root / "raw"
    if not raw_root.exists():
        return
    paths = sorted(
        (path for path in raw_root.rglob("*") if path.is_file()),
        key=lambda path: path.as_posix().casefold(),
    )
    for path in paths:
        if not include_control_files and is_control_or_temporary(
            path, raw_root, include_hidden=include_hidden
        ):
            continue
        yield path
