#!/usr/bin/env python3
"""Repository-level source registry and raw-manifest validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kg_common import issue, normalized_ref, scalar_text
from source_catalog import SourceRegistryError, iter_raw_files, load_source_records


def _raw_index(root: Path) -> set[str]:
    result: set[str] = set()
    for path in iter_raw_files(root, include_hidden=True, include_control_files=True):
        relative = path.relative_to(root).as_posix()
        for candidate in (relative, relative.removeprefix("raw/"), path.name, path.stem):
            result.add(normalized_ref(candidate))
    return result


def _validate_source_registry(root: Path, issues: list[dict[str, Any]]) -> set[str]:
    path = root / "sources" / "registry.yaml"
    relative = path.relative_to(root).as_posix()
    try:
        records = load_source_records(root)
    except SourceRegistryError as exc:
        severity, code = {
            "missing": ("high", "SOURCE_REGISTRY_MISSING"),
            "parse": ("critical", "SOURCE_REGISTRY_PARSE"),
            "type": ("critical", "SOURCE_REGISTRY_TYPE"),
        }.get(exc.kind, ("critical", "SOURCE_REGISTRY_PARSE"))
        issues.append(issue(severity, code, relative, str(exc)))
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
        changed = sorted(
            path_key
            for path_key in set(actual_by_path) & set(expected_by_path)
            if actual_by_path[path_key] != expected_by_path[path_key]
        )
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
