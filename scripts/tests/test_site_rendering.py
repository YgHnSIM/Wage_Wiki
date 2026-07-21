from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_site as build_site_module
import site_markdown
from site_mermaid import render_mermaid_flowchart


class RenderingModuleBoundaryTests(unittest.TestCase):
    def test_build_site_keeps_the_existing_rendering_import_contract(self) -> None:
        self.assertIs(build_site_module.render_inline, site_markdown.render_inline)
        self.assertIs(build_site_module.render_markdown, site_markdown.render_markdown)
        self.assertIs(build_site_module._summary, site_markdown._summary)
        self.assertIs(build_site_module._truncate_summary, site_markdown._truncate_summary)

    def test_markdown_subset_renders_the_same_structures_and_escaping(self) -> None:
        body = """# Test

## Facts

| key | value |
| --- | --- |
| status | **valid** |

- first
- second

> quote <tag>

```python
print("<safe>")
```
"""
        rendered = site_markdown.render_markdown(
            body,
            {},
            {},
            lambda slug: f"../{slug}/",
            "test-id",
            "Test",
        )
        expected = "\n".join(
            (
                '<h2 id="facts">사실관계</h2>',
                '<div class="table-wrap" tabindex="0"><table><thead><tr>'
                '<th scope="col">key</th><th scope="col">value</th></tr></thead>'
                '<tbody><tr><td>status</td><td><strong>valid</strong></td></tr></tbody></table></div>',
                "<ul><li>first</li><li>second</li></ul>",
                "<blockquote><p>quote &lt;tag&gt;</p></blockquote>",
                '<pre><code class="language-python">print(&quot;&lt;safe&gt;&quot;)</code></pre>',
            )
        )
        self.assertEqual(rendered, expected)


class MermaidRendererTests(unittest.TestCase):
    def test_rejects_cycles(self) -> None:
        source = """flowchart TD
A --> B
B --> A
"""
        with self.assertRaisesRegex(RuntimeError, "cyclic Mermaid flowcharts"):
            render_mermaid_flowchart(source, "cycle")

    def test_rejects_self_referencing_edges(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "self-referencing Mermaid flowchart"):
            render_mermaid_flowchart("flowchart TD\nA --> A\n", "self-edge")

    def test_branch_labels_and_long_edges_use_clear_separate_lanes(self) -> None:
        source = """flowchart TD
A --> B{"포괄임금약정이 성립하는가?"}
B -- "불성립" --> C["일반 임금체계로 법정수당 계산"]
B -- "성립" --> D["포함 수당과 기간 확정"]
D --> E["유형 분류"]
E --> F{"유효한가, 무효 범위는 어디까지인가?"}
F -- "전부 무효" --> C
F -- "특정 수당 범위 부정" --> G["부정된 수당은 일반 방식으로 계산"]
F -- "유효 또는 일부 무효" --> H["실제 근로시간과 통상임금 확정"]
C --> H
G --> H
H --> I["수당별 법정액 계산"]
"""
        rendered = render_mermaid_flowchart(source, "branch-routing")
        edge_paths = re.findall(r'<path d="([^"]+)" marker-end=', rendered)

        # The two rank-skipping edges must not collapse onto one outer lane.
        first_long_lane = re.search(r" L ([0-9.]+) [0-9.]+", edge_paths[1])
        second_long_lane = re.search(r" L ([0-9.]+) [0-9.]+", edge_paths[7])
        self.assertIsNotNone(first_long_lane)
        self.assertIsNotNone(second_long_lane)
        self.assertNotEqual(first_long_lane.group(1), second_long_lane.group(1))

        label_pattern = (
            r'<g class="flowchart__edge-label" transform="translate\(([0-9.]+) ([0-9.]+)\)">'
            r'<rect x="[^\"]+" y="-12" width="([0-9.]+)" height="24"></rect>'
            r'<text[^>]*>{}</text>'
        )
        left_label = re.search(label_pattern.format("전부 무효"), rendered)
        right_label = re.search(label_pattern.format("특정 수당 범위 부정"), rendered)
        center_label = re.search(label_pattern.format("유효 또는 일부 무효"), rendered)
        self.assertIsNotNone(left_label)
        self.assertIsNotNone(right_label)
        self.assertIsNotNone(center_label)
        left_x, left_width = float(left_label.group(1)), float(left_label.group(3))
        right_x, right_width = float(right_label.group(1)), float(right_label.group(3))
        self.assertGreaterEqual(
            abs(right_x - left_x),
            (left_width + right_width) / 2,
        )
        self.assertGreater(
            float(center_label.group(2)),
            max(float(left_label.group(2)), float(right_label.group(2))) + 24.0,
        )


if __name__ == "__main__":
    unittest.main()
