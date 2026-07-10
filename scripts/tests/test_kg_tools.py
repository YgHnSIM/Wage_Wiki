from __future__ import annotations

import json
import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_manifest import build_manifest
from kg_common import FrontmatterError, dump_subset_yaml, parse_frontmatter_text
from migrate_schema_v13 import _recommended_cycle


class FrontmatterTests(unittest.TestCase):
    def test_nested_evidence_and_relations(self) -> None:
        text = """---
schema_version: "1.3"
id: case-test
evidence:
  - evidence_id: ev-1
    source_id: raw-case-test
    locator: "이유 1.가"
    supports:
      - holding-001
relations:
  - relation_type: supports
    target_id: rule-test
temporal:
  applicable_from: 2024-12-19
  applicable_to: 9999-12-31
  rule_version: "2024"
  transition_note: ""
---
# body
"""
        data, body = parse_frontmatter_text(text)
        self.assertEqual(data["evidence"][0]["supports"], ["holding-001"])
        self.assertEqual(data["relations"][0]["target_id"], "rule-test")
        self.assertEqual(data["temporal"]["applicable_from"], "2024-12-19")
        self.assertIn("# body", body)

    def test_rejects_duplicate_keys(self) -> None:
        with self.assertRaises(FrontmatterError):
            parse_frontmatter_text("---\nid: one\nid: two\n---\n")

    def test_rejects_yaml_tags(self) -> None:
        with self.assertRaises(FrontmatterError):
            parse_frontmatter_text("---\nid: !!python/object:test\n---\n")

    def test_dump_round_trip(self) -> None:
        original = {
            "schema_version": "1.3",
            "id": "rule-test",
            "elements": ["요소 1"],
            "temporal": {"applicable_from": "1900-01-01", "applicable_to": "9999-12-31"},
            "evidence": [{"evidence_id": "ev-1", "supports": ["claim-1"]}],
        }
        data, _ = parse_frontmatter_text("---\n" + dump_subset_yaml(original) + "---\n")
        self.assertEqual(data, original)


class ManifestTests(unittest.TestCase):
    def test_registry_id_overrides_hash_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "raw" / "cases").mkdir(parents=True)
            (root / "sources").mkdir()
            (root / "raw" / "cases" / "decision.txt").write_text("original", encoding="utf-8")
            (root / "sources" / "registry.yaml").write_text(
                "sources:\n  - source_id: raw-case-test\n    path: raw/cases/decision.txt\n",
                encoding="utf-8",
            )
            first = build_manifest(root)
            second = build_manifest(root)
            self.assertEqual(first, second)
            self.assertEqual(first[0]["source_id"], "raw-case-test")
            self.assertEqual(len(first[0]["sha256"]), 64)

    def test_manifest_skips_placeholders_and_hidden_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "raw").mkdir()
            (root / "raw" / ".gitkeep").write_text("", encoding="utf-8")
            (root / "raw" / ".hidden-source").write_text("source", encoding="utf-8")
            (root / "raw" / "source.pdf").write_bytes(b"pdf")
            self.assertEqual([record["path"] for record in build_manifest(root)], ["raw/source.pdf"])
            included = [record["path"] for record in build_manifest(root, include_hidden=True)]
            self.assertEqual(included, ["raw/.hidden-source", "raw/source.pdf"])


class ReviewPolicyTests(unittest.TestCase):
    def test_recent_cases_are_quarterly_and_older_cases_are_annual(self) -> None:
        as_of = dt.date(2026, 7, 10)
        self.assertEqual(
            _recommended_cycle("case", "recent", {"decision_date": "2025-01-23"}, as_of),
            "quarterly",
        )
        self.assertEqual(
            _recommended_cycle("case", "older", {"decision_date": "2024-01-01"}, as_of),
            "annual",
        )


if __name__ == "__main__":
    unittest.main()
