from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_site import _truncate_summary, build_site, render_inline
from check_site import check_site
from kg_common import Entity, entity_lookup, load_entities


class SiteBuildTests(unittest.TestCase):
    def test_builds_all_entities_without_raw_sources(self) -> None:
        build_root = ROOT / "build"
        build_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=build_root) as temporary:
            output = Path(temporary)
            report = build_site(
                ROOT,
                output,
                site_url="https://example.test/Wage_Wiki/",
                repository_url="https://github.com/example/Wage_Wiki",
            )
            expected_entities = len(load_entities(ROOT)[0])
            self.assertEqual(report["entities"], expected_entities)
            self.assertTrue((output / "index.html").is_file())
            self.assertTrue((output / "about" / "index.html").is_file())
            home = (output / "index.html").read_text(encoding="utf-8")
            self.assertNotIn("시점별 길잡이", home)
            self.assertNotIn('class="featured"', home)
            self.assertNotIn('id="search-input"', home)
            self.assertNotIn('class="search-panel"', home)
            self.assertIn('class="type-filters"', home)
            self.assertIn(f"전체 문서 {expected_entities}개", home)
            for removed_control in (
                "filter-grid",
                "status-filter",
                "legal-filter",
                "date-filter",
                "sort-filter",
                "effective-filter",
                "reset-filters",
                "show-all",
            ):
                self.assertNotIn(removed_control, home)
            not_found = (output / "404.html").read_text(encoding="utf-8")
            self.assertIn('href="https://example.test/Wage_Wiki/assets/styles.css?', not_found)
            self.assertIn('href="https://example.test/Wage_Wiki/#explore"', not_found)
            self.assertEqual(len(list((output / "entities").glob("*/index.html"))), expected_entities)
            records = json.loads((output / "assets" / "entities.json").read_text(encoding="utf-8"))
            self.assertEqual(len(records), expected_entities)
            self.assertFalse(any("searchText" in record or "searchNormalised" in record for record in records))
            self.assertFalse(any("raw" in path.relative_to(output).parts for path in output.rglob("*")))
            checked = check_site(output)
            self.assertEqual(checked["issues"], 0, checked["details"])

    def test_output_must_stay_inside_repository(self) -> None:
        with self.assertRaises(ValueError):
            build_site(ROOT, ROOT)
        with self.assertRaises(ValueError):
            build_site(ROOT, ROOT / "wiki")

    def test_site_url_must_be_absolute_http_url(self) -> None:
        with self.assertRaises(ValueError):
            build_site(ROOT, ROOT / "build" / "bad-url", site_url="javascript:alert(1)")

    def test_evidence_verification_date_is_escaped(self) -> None:
        build_root = ROOT / "build"
        build_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=build_root) as temporary:
            test_root = Path(temporary) / "repo"
            (test_root / "wiki" / "cases").mkdir(parents=True)
            (test_root / "wiki" / "cases" / "test.md").write_text(
                """---
id: "case-test"
entity_type: "case"
title: "테스트 판례"
status: "review"
legal_status: "current"
evidence:
  - source_id: "raw-case-test"
    locator: "이유 1"
    excerpt: "테스트 근거"
    verified_on: "<img src=x onerror=alert(1)>"
---
# 테스트 판례

## Holding

테스트 판시사항이다.
""",
                encoding="utf-8",
            )
            output = test_root / "build" / "site"
            build_site(test_root, output, asset_source=ROOT / "web" / "assets")
            page = next((output / "entities").glob("*/index.html")).read_text(encoding="utf-8")
            self.assertNotIn("<img src=x", page)
            self.assertIn("&lt;img src=x onerror=alert(1)&gt;", page)
            self.assertIn('id="holding">판시 요약</h2>', page)

    def test_summary_truncates_at_sentence_boundary(self) -> None:
        first_sentence = "충분한 설명 " * 8 + "마친다."
        text = first_sentence + " " + "긴 설명 " * 80
        summary = _truncate_summary(text, limit=80)
        self.assertEqual(summary, first_sentence)
        self.assertFalse(summary.endswith("긴"))


class SafeMarkdownTests(unittest.TestCase):
    def test_wikilink_is_resolved_and_html_is_escaped(self) -> None:
        target = Entity(
            path=Path("target.md"),
            relative_path="wiki/rules/target.md",
            data={"id": "rule-target", "title": "연결 규칙", "entity_type": "rule", "aliases": []},
            body="",
        )
        _, names = entity_lookup([target])
        rendered = render_inline(
            "<script>alert(1)</script> [[연결 규칙|규칙 보기]]",
            names,
            {"rule-target": "rule-target-a1b2c3d4"},
            lambda slug: f"../{slug}/",
        )
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn('href="../rule-target-a1b2c3d4/"', rendered)
        self.assertIn("규칙 보기", rendered)


if __name__ == "__main__":
    unittest.main()
