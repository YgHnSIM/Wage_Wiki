from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
