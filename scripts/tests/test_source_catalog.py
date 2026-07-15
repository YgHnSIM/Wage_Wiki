from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from lint_sources import _validate_source_registry
from source_catalog import (
    SourceRegistryError,
    iter_raw_files,
    load_source_records,
    registry_ids,
    registry_path_map,
    registry_title_map,
)


class SourceRegistryTests(unittest.TestCase):
    def test_derived_registry_views_share_one_parse(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "raw" / "cases" / "decision.html"
            source.parent.mkdir(parents=True)
            source.write_text("decision", encoding="utf-8")
            registry = root / "sources" / "registry.yaml"
            registry.parent.mkdir(parents=True)
            registry.write_text(
                """sources:
  - source_id: "raw-case-test"
    title: "테스트 판결"
    path: "raw/cases/decision.html"
""",
                encoding="utf-8",
            )

            self.assertEqual(len(load_source_records(root)), 1)
            self.assertEqual(registry_ids(root), {"raw-case-test"})
            self.assertEqual(
                registry_path_map(root), {"raw/cases/decision.html": "raw-case-test"}
            )
            self.assertEqual(registry_title_map(root), {"raw-case-test": "테스트 판결"})

    def test_strict_loader_and_lint_adapter_preserve_error_categories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(SourceRegistryError, "does not exist") as raised:
                load_source_records(root)
            self.assertEqual(raised.exception.kind, "missing")

            issues: list[dict[str, object]] = []
            _validate_source_registry(root, issues)
            self.assertEqual(
                [(item["severity"], item["code"]) for item in issues],
                [("high", "SOURCE_REGISTRY_MISSING")],
            )

            registry = root / "sources" / "registry.yaml"
            registry.parent.mkdir(parents=True)
            registry.write_text("sources: {}\n", encoding="utf-8")
            issues = []
            _validate_source_registry(root, issues)
            self.assertEqual(issues[0]["code"], "SOURCE_REGISTRY_TYPE")
            self.assertEqual(issues[0]["severity"], "critical")


class RawFilePolicyTests(unittest.TestCase):
    def test_generation_and_validation_inclusion_modes_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = root / "raw"
            raw.mkdir()
            for name in ("source.pdf", ".hidden.pdf", "download.tmp", ".gitkeep"):
                (raw / name).write_text(name, encoding="utf-8")

            public = {path.name for path in iter_raw_files(root)}
            with_hidden = {path.name for path in iter_raw_files(root, include_hidden=True)}
            validation = {
                path.name
                for path in iter_raw_files(
                    root,
                    include_hidden=True,
                    include_control_files=True,
                )
            }
            self.assertEqual(public, {"source.pdf"})
            self.assertEqual(with_hidden, {"source.pdf", ".hidden.pdf"})
            self.assertEqual(
                validation,
                {"source.pdf", ".hidden.pdf", "download.tmp", ".gitkeep"},
            )


if __name__ == "__main__":
    unittest.main()
