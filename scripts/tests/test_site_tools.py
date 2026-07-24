from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_site import _summary, _truncate_summary, build_site, render_inline, render_markdown
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
            self.assertIn('class="judgment-paths"', home)
            self.assertIn('class="topic-index"', home)
            self.assertIn('id="search-input"', home)
            self.assertIn('class="search-panel"', home)
            self.assertIn('class="type-filters"', home)
            self.assertIn('data-type="guide" data-label="실무 가이드"', home)
            self.assertIn('<main id="main" tabindex="-1">', home)
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
            self.assertEqual(records[0]["type"], "guide")
            self.assertEqual(records[0]["number"], "GU-01")
            self.assertTrue(all(record.get("searchText") for record in records))
            self.assertTrue(all("aliases" in record and "caseNumber" in record for record in records))
            self.assertLessEqual(max(len(record["summary"]) for record in records), 161)
            self.assertFalse(any("raw" in path.relative_to(output).parts for path in output.rglob("*")))
            flowchart_pages = []
            temporal_metadata_pages = []
            for page_path in (output / "entities").glob("*/index.html"):
                page = page_path.read_text(encoding="utf-8")
                if "<h1>보장시간 합의 후 법정수당 재산정</h1>" in page:
                    flowchart_pages.append(page)
                if "<h1>대법원 2013. 12. 18. 선고 2012다89399 전원합의체 판결</h1>" in page:
                    temporal_metadata_pages.append(page)
                relation_aside = re.search(r'<aside class="relations".*?</aside>', page, flags=re.S)
                if not relation_aside:
                    continue
                targets = re.findall(r'<a href="(\.\./[^\"]+/)">', relation_aside.group(0))
                self.assertEqual(len(targets), len(set(targets)), page_path.name)
            self.assertEqual(len(flowchart_pages), 1)
            self.assertEqual(flowchart_pages[0].count('<figure class="flowchart '), 2)
            self.assertEqual(flowchart_pages[0].count('<svg class="flowchart__svg"'), 2)
            self.assertNotIn("language-mermaid", flowchart_pages[0])
            self.assertEqual(len(temporal_metadata_pages), 1)
            primary_metadata = re.search(
                r'<dl class="document-meta__primary">(.*?)</dl>', temporal_metadata_pages[0], flags=re.S
            )
            self.assertIsNotNone(primary_metadata)
            self.assertIn('class="document-meta__row--period-start"', primary_metadata.group(1))
            self.assertIn('class="document-meta__row--period-end"', primary_metadata.group(1))
            self.assertIn("<dt>적용 시작</dt><dd>2013. 12. 18.</dd>", primary_metadata.group(1))
            self.assertIn("<dt>적용 종료</dt><dd>종료일 없음</dd>", primary_metadata.group(1))
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
            self.assertIn("등록 원문", page)

    def test_summary_truncates_at_sentence_boundary(self) -> None:
        first_sentence = "충분한 설명 " * 8 + "마친다."
        text = first_sentence + " " + "긴 설명 " * 80
        summary = _truncate_summary(text, limit=80)
        self.assertEqual(summary, first_sentence)
        self.assertFalse(summary.endswith("긴"))

    def test_structured_summary_is_also_limited(self) -> None:
        entity = Entity(
            path=Path("test.md"),
            relative_path="wiki/cases/test.md",
            data={"holding_summary": "판시 내용 " * 80},
            body="",
        )
        self.assertLessEqual(len(_summary(entity)), 161)

    def test_body_summary_stops_before_markdown_table(self) -> None:
        entity = Entity(
            path=Path("test.md"),
            relative_path="wiki/history/test.md",
            data={},
            body="""# Timeline

The opening paragraph explains the timeline.

| Year | Event |
| --- | --- |
| 2024 | Changed |
""",
        )
        self.assertEqual(_summary(entity), "The opening paragraph explains the timeline.")


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

    def test_mermaid_flowchart_is_rendered_as_safe_static_svg(self) -> None:
        body = """# 테스트

```mermaid
flowchart LR
    A["<script>alert(1)</script> 시작"] --> B{"판단할 것인가?"}
    B -- "예" --> C["결론"]
```
"""
        rendered = render_markdown(body, {}, {}, lambda slug: slug, "fact-test", "테스트")
        self.assertIn('<figure class="flowchart flowchart--horizontal-source"', rendered)
        self.assertIn('<svg class="flowchart__svg"', rendered)
        self.assertIn('class="flowchart__node flowchart__node--decision"', rendered)
        self.assertIn('class="flowchart__edge-label"', rendered)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; 시작", rendered)
        self.assertNotIn("<script>alert(1)</script>", rendered)
        self.assertNotIn("language-mermaid", rendered)

    def test_unsupported_mermaid_diagram_fails_the_build(self) -> None:
        body = """# 테스트

```mermaid
sequenceDiagram
    A->>B: 요청
```
"""
        with self.assertRaisesRegex(RuntimeError, "only Mermaid flowchart"):
            render_markdown(body, {}, {}, lambda slug: slug, "fact-test", "테스트")


if __name__ == "__main__":
    unittest.main()
