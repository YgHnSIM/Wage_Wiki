#!/usr/bin/env python3
"""Search the generated Wage Wiki FTS index with temporal and legal-status filters."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--database", type=Path, default=Path("build/wage_wiki.sqlite"))
    parser.add_argument("--as-of", default=dt.date.today().isoformat())
    parser.add_argument("--status", default="verified")
    parser.add_argument("--legal-status", default="current")
    parser.add_argument("--include-review", action="store_true")
    parser.add_argument("--include-historical", action="store_true")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    connection = sqlite3.connect(args.database)
    connection.row_factory = sqlite3.Row
    try:
        clauses = ["chunks_fts MATCH ?", "c.effective_from <= ?", "c.effective_to >= ?"]
        params: list[object] = [args.query, args.as_of, args.as_of]
        if args.include_review:
            clauses.append("c.status IN ('verified', 'review')")
        else:
            clauses.append("c.status = ?")
            params.append(args.status)
        if not args.include_historical:
            clauses.append("c.legal_status = ?")
            params.append(args.legal_status)
        params.append(max(1, args.limit))
        rows = connection.execute(
            f"""
            SELECT c.chunk_id, c.entity_id, c.title, c.heading, c.path,
                   c.status, c.legal_status, bm25(chunks_fts, 0.0, 2.0, 1.0, 1.0) AS rank,
                   snippet(chunks_fts, 3, '[', ']', ' … ', 24) AS snippet
            FROM chunks_fts
            JOIN chunks c ON c.chunk_id = chunks_fts.chunk_id
            WHERE {' AND '.join(clauses)}
            ORDER BY rank, c.title, c.heading
            LIMIT ?
            """,
            params,
        ).fetchall()
        print(json.dumps([dict(row) for row in rows], ensure_ascii=False, indent=2))
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
