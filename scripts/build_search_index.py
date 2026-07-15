#!/usr/bin/env python3
"""Build deterministic section chunks and a local SQLite FTS5 search index."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from claim_contract import (
    HEADING_RE,
    body_plain_text,
    fence_closes,
    fence_spec,
    markdown_plain_text,
    strip_claim_markers,
)
from kg_common import load_entities, scalar_text


def plain_text(text: str) -> str:
    return body_plain_text(text)


def section_chunks(body: str) -> list[tuple[str, str]]:
    heading = "본문"
    lines: list[str] = []
    result: list[tuple[str, str]] = []
    fence: tuple[str, int] | None = None
    for line in strip_claim_markers(body).splitlines():
        if fence is not None:
            if fence_closes(line, *fence):
                fence = None
            continue
        opener = fence_spec(line)
        if opener is not None:
            fence = opener[:2]
            continue
        match = HEADING_RE.match(line)
        if match:
            content = markdown_plain_text("\n".join(lines))
            if content:
                result.append((heading, content))
            # Heading claim-like text is deliberately not rescanned as prose:
            # headings cannot own claim anchors, so rejected markers stay visible.
            heading = markdown_plain_text(match.group(2))
            lines = []
        else:
            lines.append(line)
    content = markdown_plain_text("\n".join(lines))
    if content:
        result.append((heading, content))
    return result


def build_chunks(root: Path) -> list[dict[str, str]]:
    entities, parse_issues = load_entities(root)
    if parse_issues:
        messages = "; ".join(item["message"] for item in parse_issues[:5])
        raise RuntimeError(f"frontmatter parse failed: {messages}")
    chunks: list[dict[str, str]] = []
    for entity in entities:
        data = entity.data
        entity_id = scalar_text(data.get("id"))
        if not entity_id:
            continue
        for index, (heading, content) in enumerate(section_chunks(entity.body), 1):
            chunks.append({
                "chunk_id": f"{entity_id}::section-{index:03d}",
                "entity_id": entity_id,
                "title": scalar_text(data.get("title")) or entity.path.stem,
                "entity_type": scalar_text(data.get("entity_type")),
                "status": scalar_text(data.get("status")),
                "legal_status": scalar_text(data.get("legal_status")) or "unknown",
                "effective_from": scalar_text(data.get("effective_from")) or "1900-01-01",
                "effective_to": scalar_text(data.get("effective_to")) or "9999-12-31",
                "heading": heading,
                "content": content,
                "path": entity.relative_path,
            })
    return sorted(chunks, key=lambda item: item["chunk_id"])


def write_jsonl(chunks: list[dict[str, str]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    rendered = "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in chunks)
    output.write_text(rendered, encoding="utf-8", newline="\n")


def write_sqlite(chunks: list[dict[str, str]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    connection = sqlite3.connect(output)
    try:
        connection.executescript(
            """
            PRAGMA journal_mode=DELETE;
            CREATE TABLE chunks (
              chunk_id TEXT PRIMARY KEY,
              entity_id TEXT NOT NULL,
              title TEXT NOT NULL,
              entity_type TEXT NOT NULL,
              status TEXT NOT NULL,
              legal_status TEXT NOT NULL,
              effective_from TEXT NOT NULL,
              effective_to TEXT NOT NULL,
              heading TEXT NOT NULL,
              content TEXT NOT NULL,
              path TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE chunks_fts USING fts5(
              chunk_id UNINDEXED,
              title,
              heading,
              content,
              tokenize='unicode61'
            );
            """
        )
        columns = (
            "chunk_id", "entity_id", "title", "entity_type", "status", "legal_status",
            "effective_from", "effective_to", "heading", "content", "path",
        )
        connection.executemany(
            f"INSERT INTO chunks ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
            ([item[column] for column in columns] for item in chunks),
        )
        connection.executemany(
            "INSERT INTO chunks_fts (chunk_id,title,heading,content) VALUES (?,?,?,?)",
            ((item["chunk_id"], item["title"], item["heading"], item["content"]) for item in chunks),
        )
        connection.execute("CREATE INDEX chunks_entity_id_idx ON chunks(entity_id)")
        connection.execute("CREATE INDEX chunks_temporal_idx ON chunks(effective_from,effective_to)")
        connection.commit()
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--chunks", type=Path, default=Path("derived/chunks.jsonl"))
    parser.add_argument("--database", type=Path, default=Path("build/wage_wiki.sqlite"))
    args = parser.parse_args()
    root = args.root.resolve()
    chunks = build_chunks(root)
    chunks_path = args.chunks if args.chunks.is_absolute() else root / args.chunks
    database_path = args.database if args.database.is_absolute() else root / args.database
    write_jsonl(chunks, chunks_path)
    write_sqlite(chunks, database_path)
    print(json.dumps({"chunks": len(chunks), "jsonl": str(chunks_path), "database": str(database_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
