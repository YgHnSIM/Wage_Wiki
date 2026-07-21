#!/usr/bin/env python3
"""Generate a static Markdown quality dashboard without requiring Dataview."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from kg_common import SCHEMA_VERSION, load_entities, scalar_text
from lint_wiki import lint_repository
from temporal_policy import repository_today


def _table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    result = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    result.extend("| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |" for row in rows)
    return result


def build_dashboard(root: Path, today: dt.date | None = None) -> str:
    root = root.resolve()
    today = today or repository_today()
    entities, _ = load_entities(root)
    report = lint_repository(root, today=today)
    by_type = Counter(scalar_text(entity.data.get("entity_type")) for entity in entities)
    by_status = Counter(scalar_text(entity.data.get("status")) or "missing" for entity in entities)
    by_legal = Counter(scalar_text(entity.data.get("legal_status")) or "unmigrated" for entity in entities)
    summary = report["summary"]
    lines = [
        "# Wage Wiki 품질 대시보드",
        "",
        f"- 기준일: {today.isoformat()}",
        f"- 스키마: {SCHEMA_VERSION}",
        f"- 엔티티: {summary['entities']}",
        f"- 전체 이슈: {summary['issues']}",
        "",
        "## 심각도",
        "",
    ]
    lines += _table(["심각도", "건수"], [[key, value] for key, value in summary["by_severity"].items()])
    lines += ["", "## 엔티티 유형", ""]
    lines += _table(["entity_type", "건수"], [[key, by_type[key]] for key in sorted(by_type)])
    lines += ["", "## 편집 상태", ""]
    lines += _table(["status", "건수"], [[key, by_status[key]] for key in sorted(by_status)])
    lines += ["", "## 법적 상태", ""]
    lines += _table(["legal_status", "건수"], [[key, by_legal[key]] for key in sorted(by_legal)])
    lines += ["", "## 우선 조치", ""]
    priority = [item for item in report["issues"] if item["severity"] in {"critical", "high"}]
    if priority:
        lines += _table(
            ["심각도", "코드", "문서", "내용"],
            [[item["severity"], item["code"], item["path"], item["message"]] for item in priority[:100]],
        )
    else:
        lines.append("Critical/High 이슈가 없습니다.")
    lines += ["", "> 이 문서는 scripts/build_dashboard.py가 생성합니다. 직접 편집하지 마세요.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, help="write Markdown here; stdout when omitted")
    parser.add_argument("--today", type=dt.date.fromisoformat)
    args = parser.parse_args(argv)
    rendered = build_dashboard(args.root, args.today)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
