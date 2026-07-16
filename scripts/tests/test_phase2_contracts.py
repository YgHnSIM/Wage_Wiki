from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from authority_policy import authority_diagnostics, inferred_authority_levels
from build_site import _resolved_claim_ids
from build_search_index import plain_text, section_chunks
from claim_contract import (
    body_plain_text,
    claim_anchors,
    evidence_claim_ids,
    global_claim_id,
    global_evidence_id,
    global_source_id,
    resolved_claim_ids,
    validate_claim_anchors,
)
from export_graph import GRAPH_SCHEMA_VERSION, export_graph
from kg_common import Entity, as_list, load_entities
from lint_wiki import (
    _validate_dates,
    _validate_evidence,
    _validate_list_of_strings,
    _validate_relations,
    lint_repository,
)
from migrate_verification_metadata import main as migrate_verification_main, migrate_data
from plan_claim_anchors import plan_entity
from schema_contract import load_schema_contract
from site_markdown import _summary, render_markdown
from temporal_policy import supersession_diagnostics
from verification_contract import (
    VerifierRegistryError,
    has_verifier_identity,
    load_verifier_registry,
    normalize_legacy_verification,
    validate_verification,
)
from verification_policy import verification_timeline_diagnostics


def _entity(data: dict[str, object], body: str = "") -> Entity:
    return Entity(Path("fixture.md"), "wiki/fixture.md", data, body)


def _copy_migration_contract(root: Path) -> None:
    schemas = root / "schemas"
    schemas.mkdir(exist_ok=True)
    for name in (
        "frontmatter-v1.3.schema.json",
        "vocabularies.json",
        "verifiers.json",
    ):
        shutil.copy2(ROOT / "schemas" / name, schemas / name)


class ClaimAnchorContractTests(unittest.TestCase):
    def test_extracts_paragraph_list_and_standalone_markers_but_ignores_code(self) -> None:
        body = """문단 주장. ^claim-one

- 목록 주장 ^claim-two

별도 문단 주장.
^claim-three

```text
코드 ^claim-code
```
"""
        anchors = claim_anchors(body)
        self.assertEqual(
            [(anchor.claim_id, anchor.text) for anchor in anchors],
            [
                ("claim-one", "문단 주장."),
                ("claim-two", "목록 주장"),
                ("claim-three", "별도 문단 주장."),
            ],
        )

    def test_strict_resolution_reports_each_missing_local_claim_once(self) -> None:
        data = {
            "evidence": [
                {"supports": ["claim-one", "claim-two"]},
                {"supports": ["claim-one"]},
            ]
        }
        problems = validate_claim_anchors(data, "문단. ^claim-one\n", require_anchors=True)
        self.assertEqual([problem.code for problem in problems], ["EVIDENCE_CLAIM_UNRESOLVED"])
        self.assertIn("claim-two", problems[0].message)

    def test_site_and_search_consumers_hide_marker_and_preserve_fragment(self) -> None:
        body = """# Test

주장 문단. ^claim-one

- 목록 주장 ^claim-two
"""
        rendered = render_markdown(body, {}, {}, lambda slug: slug, "test", "Test")
        self.assertIn('<p id="claim-one">주장 문단.</p>', rendered)
        self.assertIn('<li id="claim-two">목록 주장</li>', rendered)
        self.assertNotIn("^claim", rendered)
        self.assertEqual(plain_text("주장 문단. ^claim-one"), "주장 문단.")
        self.assertEqual(
            plain_text("literal ^claim-one reference"),
            "literal ^claim-one reference",
        )

    def test_rejects_markers_that_the_site_cannot_render_as_fragments(self) -> None:
        heading = "## Facts ^claim-one\n"
        problems = validate_claim_anchors(
            {"evidence": [{"supports": ["claim-one"]}]},
            heading,
            require_anchors=True,
        )
        self.assertEqual(
            [problem.code for problem in problems],
            ["CLAIM_MARKER_CONTEXT", "EVIDENCE_CLAIM_UNRESOLVED"],
        )
        self.assertNotIn(
            'id="claim-one"',
            render_markdown(heading, {}, {}, lambda slug: slug, "test", "Test"),
        )

        consecutive = "First. ^claim-one\nSecond. ^claim-two\n"
        problems = validate_claim_anchors(
            {"evidence": [{"supports": ["claim-one", "claim-two"]}]},
            consecutive,
            require_anchors=True,
        )
        self.assertEqual([anchor.claim_id for anchor in claim_anchors(consecutive)], ["claim-two"])
        self.assertEqual(
            [problem.code for problem in problems],
            ["CLAIM_MARKER_CONTEXT", "EVIDENCE_CLAIM_UNRESOLVED"],
        )

    def test_long_and_tilde_fences_share_scanner_and_renderer_boundaries(self) -> None:
        for body in (
            "````text\n```\ncode ^claim-one\n````\n",
            "Before.\n~~~text\ncode ^claim-one\n~~~\n",
        ):
            with self.subTest(body=body):
                self.assertEqual(claim_anchors(body), ())
                rendered = render_markdown(body, {}, {}, lambda slug: slug, "test", "Test")
                self.assertNotIn('id="claim-one"', rendered)
                self.assertIn("code ^claim-one", rendered)

    def test_rejects_empty_blocks_and_fragment_namespace_collisions(self) -> None:
        for body in ("- ^claim-one\n", "> ^claim-one\n"):
            with self.subTest(body=body):
                problems = validate_claim_anchors({}, body)
                self.assertIn("CLAIM_BLOCK_EMPTY", [problem.code for problem in problems])
        collision = "## [Facts](https://example.invalid)\n\nText. ^facts\n"
        problems = validate_claim_anchors({}, collision)
        self.assertEqual([problem.code for problem in problems], ["CLAIM_FRAGMENT_COLLISION"])

        skipped_title = "# My Title\n\nText. ^my-title\n"
        self.assertEqual(
            validate_claim_anchors({"title": "My Title"}, skipped_title),
            (),
        )

    def test_site_summary_and_search_share_marker_and_markdown_plain_text(self) -> None:
        body = "Text **bold** [label](https://example.invalid) ^claim-one"
        self.assertEqual(body_plain_text(body), "Text bold label")
        self.assertEqual(plain_text(body), "Text bold label")
        self.assertEqual(
            plain_text("literal ^claim-one reference"),
            "literal ^claim-one reference",
        )
        self.assertEqual(
            body_plain_text("133~267% source_availability #tag"),
            "133~267% source_availability #tag",
        )
        self.assertEqual(
            section_chunks("## Facts ^claim-one\n\nText\n"),
            [("Facts ^claim-one", "Text")],
        )
        self.assertEqual(
            section_chunks("```text\n## Not a heading\nsecret\n```\n\nVisible.\n"),
            [("본문", "Visible.")],
        )
        entity = _entity({"title": "One"}, "~~~text\nsecret ^claim-one\n~~~\n\nVisible.\n")
        self.assertEqual(_summary(entity), "Visible.")
        self.assertEqual(_resolved_claim_ids("Text. ^BAD\n"), set())
        self.assertEqual(
            _resolved_claim_ids("## Facts\n\nText. ^facts\n", "Other Title"),
            set(),
        )

    def test_repository_claim_plan_is_explicitly_unresolved(self) -> None:
        entities, parse_issues = load_entities(ROOT)
        self.assertEqual(parse_issues, [])
        plans = [plan for entity in entities if (plan := plan_entity(entity)) is not None]
        claims = [claim for plan in plans for claim in plan["claims"]]
        expected = sum(len(evidence_claim_ids(entity.data.get("evidence"))) for entity in entities)
        self.assertEqual(len(claims), expected)
        self.assertEqual(len(plans), sum(bool(evidence_claim_ids(entity.data.get("evidence"))) for entity in entities))
        self.assertLessEqual(sum(bool(claim["resolved"]) for claim in claims), len(claims))
        self.assertTrue(all(claim["valid_id"] for claim in claims))


class VerificationMetadataContractTests(unittest.TestCase):
    def test_exact_legacy_values_map_without_rewriting_legacy_field(self) -> None:
        token, unknown = normalize_legacy_verification(["codex-official-source-review"])
        self.assertEqual(unknown, ())
        self.assertEqual(
            token,
            {"verifier_ids": ["codex"], "methods": ["official_source_review"], "note": ""},
        )
        prose, unknown = normalize_legacy_verification(["Codex 공식 원문·연구문헌 대조"])
        self.assertEqual(unknown, ())
        self.assertEqual(
            prose,
            {"verifier_ids": ["codex"], "methods": ["source_cross_check"], "note": "공식 원문·연구문헌"},
        )

    def test_migration_is_additive_and_idempotent(self) -> None:
        original = {
            "id": "case-test",
            "entity_type": "case",
            "verified_by": ["Codex 공식 원문 대조"],
            "last_verified": "2026-07-10",
        }
        migrated, first = migrate_data(original)
        self.assertTrue(first["changed"])
        self.assertEqual(migrated["verified_by"], original["verified_by"])
        again, second = migrate_data(migrated)
        self.assertFalse(second["changed"])
        self.assertFalse(second["existing_metadata_conflict"])
        self.assertEqual(again, migrated)

    def test_exact_allowlist_placeholder_and_drift_are_enforced(self) -> None:
        _, unknown = normalize_legacy_verification(["Codex 임의 자료 대조"])
        self.assertEqual(unknown, ("Codex 임의 자료 대조",))

        template = {
            "verified_by": ["codex-official-source-review"],
            "verification": {"verifier_ids": [], "methods": [], "note": ""},
        }
        migrated, first = migrate_data(template)
        self.assertTrue(first["changed"])
        self.assertFalse(first["existing_metadata_conflict"])
        _, second = migrate_data(migrated)
        self.assertFalse(second["changed"])
        self.assertFalse(second["existing_metadata_conflict"])

        drift = dict(migrated)
        drift["verification"] = {
            "verifier_ids": ["codex"],
            "methods": ["source_cross_check"],
            "note": "공식 원문",
        }
        problems = validate_verification(
            drift,
            {"codex"},
            {"official_source_review", "source_cross_check"},
        )
        self.assertIn("VERIFICATION_LEGACY_DRIFT", [problem.code for problem in problems])

    def test_migration_uses_semantic_comparison_and_blocks_malformed_existing_data(self) -> None:
        data = {
            "verified_by": [
                "codex-official-source-review",
                "Codex 공식 원문 대조",
            ],
            "verification": {
                "verifier_ids": ["codex"],
                "methods": ["source_cross_check", "official_source_review"],
                "note": "공식 원문",
            },
        }
        _, equivalent = migrate_data(data)
        self.assertFalse(equivalent["existing_metadata_conflict"])
        for malformed in ("bad", [], 42):
            with self.subTest(malformed=malformed):
                bad = dict(data, verification=malformed)
                _, details = migrate_data(bad)
                self.assertTrue(details["existing_metadata_conflict"])

    def test_blank_legacy_values_do_not_create_metadata_or_identity(self) -> None:
        migrated, details = migrate_data({"verified_by": [""]})
        self.assertFalse(details["changed"])
        self.assertNotIn("verification", migrated)
        self.assertFalse(has_verifier_identity({"verified_by": [""]}))
        self.assertTrue(
            has_verifier_identity(
                {"verification": {"verifier_ids": ["alice"], "methods": [], "note": ""}}
            )
        )

    def test_cli_blocks_all_writes_when_any_metadata_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _copy_migration_contract(root)
            wiki = root / "wiki"
            wiki.mkdir()
            eligible = wiki / "eligible.md"
            eligible.write_text(
                """---
id: "eligible"
entity_type: "case"
verified_by:
  - "codex-official-source-review"
---
# Eligible
""",
                encoding="utf-8",
            )
            conflict = wiki / "conflict.md"
            conflict.write_text(
                """---
id: "conflict"
entity_type: "case"
verified_by:
  - "codex-official-source-review"
verification:
  verifier_ids:
    - "codex"
  methods:
    - "source_cross_check"
  note: "different"
---
# Conflict
""",
                encoding="utf-8",
            )
            original = eligible.read_text(encoding="utf-8")
            output = root / "report.json"
            return_code = migrate_verification_main(
                ["--root", str(root), "--write", "--output", str(output)]
            )
            report = json.loads(output.read_text(encoding="utf-8"))
            after = eligible.read_text(encoding="utf-8")
        self.assertEqual(return_code, 1)
        self.assertTrue(report["summary"]["write_blocked"])
        self.assertEqual(report["summary"]["files_changed"], 0)
        self.assertEqual(after, original)

    def test_cli_rolls_back_all_files_when_replace_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _copy_migration_contract(root)
            wiki = root / "wiki"
            wiki.mkdir()
            originals: dict[Path, str] = {}
            for name in ("one", "two"):
                path = wiki / f"{name}.md"
                path.write_text(
                    f"""---
id: "{name}"
entity_type: "case"
verified_by:
  - "codex-official-source-review"
---
# {name}
""",
                    encoding="utf-8",
                )
                originals[path] = path.read_text(encoding="utf-8")
            output = root / "report.json"
            real_replace = os.replace
            calls = 0

            def fail_second_replace(source: str | os.PathLike[str], target: str | os.PathLike[str]) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected replace failure")
                real_replace(source, target)

            with patch("migrate_verification_metadata.os.replace", side_effect=fail_second_replace):
                return_code = migrate_verification_main(
                    ["--root", str(root), "--write", "--output", str(output)]
                )
            report = json.loads(output.read_text(encoding="utf-8"))
            after = {path: path.read_text(encoding="utf-8") for path in originals}
            leftovers = list(wiki.glob("*.verification-*.tmp")) + list(
                wiki.glob(".*.verification-*.tmp")
            )
        self.assertEqual(return_code, 1)
        self.assertTrue(report["summary"]["write_error"])
        self.assertEqual(report["summary"]["files_changed"], 0)
        self.assertEqual(after, originals)
        self.assertEqual(leftovers, [])

    def test_cli_preflights_static_mappings_and_validates_existing_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _copy_migration_contract(root)
            registry_path = root / "schemas" / "verifiers.json"
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            registry["verifiers"] = {
                "alice": {"display_name": "Alice", "kind": "human"}
            }
            registry_path.write_text(json.dumps(registry), encoding="utf-8")
            (root / "wiki").mkdir()
            output = root / "mapping-report.json"
            return_code = migrate_verification_main(
                ["--root", str(root), "--output", str(output)]
            )
            report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(return_code, 1)
        self.assertIn(
            "VERIFICATION_VERIFIER_MAPPING_DRIFT",
            {item["code"] for item in report["preflight_issues"]},
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _copy_migration_contract(root)
            registry_path = root / "schemas" / "verifiers.json"
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            registry["verifiers"]["alice"] = {
                "display_name": "Alice",
                "kind": "human",
            }
            registry_path.write_text(json.dumps(registry), encoding="utf-8")
            wiki = root / "wiki"
            wiki.mkdir()
            (wiki / "bad.md").write_text(
                """---
id: "bad"
entity_type: "case"
verified_by:
  - "alice"
verification:
  verifier_ids:
    - "alice"
  methods:
    - "bogus"
  note: ""
---
Bad.
""",
                encoding="utf-8",
            )
            output = root / "validation-report.json"
            return_code = migrate_verification_main(
                ["--root", str(root), "--output", str(output)]
            )
            report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(return_code, 1)
        self.assertEqual(report["summary"]["verification_validation_problem"], 1)

    def test_registry_and_nested_method_vocabulary_validate_current_data(self) -> None:
        registry = load_verifier_registry(ROOT)
        contract = load_schema_contract(ROOT)
        self.assertEqual(registry.ids, frozenset({"codex"}))
        self.assertEqual(
            contract.verification_methods,
            frozenset({"official_source_review", "source_cross_check"}),
        )
        entities, _ = load_entities(ROOT)
        structured = [entity for entity in entities if isinstance(entity.data.get("verification"), dict)]
        self.assertEqual(len(structured), 63)
        problems = [
            problem
            for entity in structured
            for problem in validate_verification(
                entity.data,
                registry.ids,
                contract.verification_methods,
            )
        ]
        self.assertEqual(problems, [])

    def test_registry_contract_rejects_invalid_versions_ids_and_records(self) -> None:
        invalid_values = (
            {"schema_version": "2.0", "verifiers": {"codex": {"display_name": "Codex", "kind": "ai"}}},
            {"schema_version": "1.0", "verifiers": {" Codex": {"display_name": "Codex", "kind": "ai"}}},
            {"schema_version": "1.0", "verifiers": {"codex": {}}},
            {"schema_version": "1.0", "verifiers": {"codex": {"display_name": 1, "kind": "ai"}}},
            {"schema_version": "1.0", "verifiers": {"codex": {"display_name": "Codex", "kind": "ai", "description": 1}}},
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            schemas = root / "schemas"
            schemas.mkdir()
            path = schemas / "verifiers.json"
            for value in invalid_values:
                with self.subTest(value=value):
                    path.write_text(json.dumps(value), encoding="utf-8")
                    with self.assertRaises(VerifierRegistryError):
                        load_verifier_registry(root)

    def test_cross_check_requires_note(self) -> None:
        problems = validate_verification(
            {
                "verification": {
                    "verifier_ids": ["codex"],
                    "methods": ["source_cross_check"],
                    "note": "",
                }
            },
            {"codex"},
            {"source_cross_check"},
        )
        self.assertEqual([problem.code for problem in problems], ["VERIFICATION_NOTE_MISSING"])

    def test_rejects_empty_values_and_unknown_fields(self) -> None:
        problems = validate_verification(
            {
                "verification": {
                    "verifier_ids": [""],
                    "methods": [""],
                    "note": "",
                    "extra": "not-allowed",
                }
            },
            {"codex"},
            {"official_source_review"},
        )
        self.assertEqual(
            [problem.code for problem in problems],
            [
                "VERIFICATION_FIELD_UNKNOWN",
                "VERIFIER_ID_INVALID",
                "VERIFICATION_METHOD_INVALID",
            ],
        )
        null = validate_verification({"verification": None}, {"codex"}, {"official_source_review"})
        self.assertEqual([problem.code for problem in null], ["VERIFICATION_TYPE"])

    def test_rejects_spaced_raw_values_and_accepts_registry_ids(self) -> None:
        spaced = validate_verification(
            {
                "verification": {
                    "verifier_ids": [" codex "],
                    "methods": [" official_source_review "],
                    "note": "",
                }
            },
            {"codex"},
            {"official_source_review"},
        )
        self.assertEqual(
            [problem.code for problem in spaced],
            ["VERIFIER_ID_INVALID", "VERIFICATION_METHOD_INVALID"],
        )
        direct = {
            "verified_by": ["alice"],
            "verification": {
                "verifier_ids": ["alice"],
                "methods": ["official_source_review"],
                "note": "",
            },
        }
        self.assertEqual(
            validate_verification(direct, {"alice"}, {"official_source_review"}),
            (),
        )
        self.assertEqual(validate_verification(direct, None, None), ())
        _, migration = migrate_data(direct, {"alice"})
        self.assertEqual(migration["unknown_legacy_values"], [])
        self.assertFalse(migration["existing_metadata_conflict"])
        for spaced in (" alice ", "alice\n"):
            with self.subTest(spaced=spaced):
                spaced_data = dict(direct, verified_by=[spaced])
                problems = validate_verification(
                    spaced_data,
                    {"alice"},
                    {"official_source_review"},
                )
                self.assertIn(
                    "VERIFICATION_LEGACY_UNKNOWN",
                    [problem.code for problem in problems],
                )
                _, details = migrate_data(spaced_data, {"alice"})
                self.assertEqual(details["unknown_legacy_values"], [spaced])


class EvidenceSchemaParityTests(unittest.TestCase):
    def test_evidence_types_unknown_fields_and_unique_supports_match_schema(self) -> None:
        entity = _entity(
            {
                "evidence": [
                    {
                        "evidence_id": 123,
                        "source_id": "src",
                        "locator": 5,
                        "supports": ["claim-one", "claim-one"],
                        "extra": "x",
                    }
                ]
            }
        )
        issues: list[dict[str, object]] = []
        _validate_evidence(entity, {"src"}, issues)
        self.assertEqual(
            {item["code"] for item in issues},
            {
                "EVIDENCE_FIELD_UNKNOWN",
                "EVIDENCE_ID",
                "EVIDENCE_LOCATOR",
                "EVIDENCE_SUPPORTS_DUPLICATE",
            },
        )

    def test_evidence_whitespace_claim_is_not_silently_discarded(self) -> None:
        entity = _entity(
            {
                "evidence": [
                    {
                        "evidence_id": "ev-1",
                        "source_id": "src",
                        "locator": "p. 1",
                        "supports": [" "],
                    }
                ]
            }
        )
        issues: list[dict[str, object]] = []
        _validate_evidence(entity, {"src"}, issues)
        self.assertEqual([item["code"] for item in issues], ["EVIDENCE_SUPPORTS"])

    def test_evidence_ids_and_locators_must_not_be_whitespace(self) -> None:
        entity = _entity(
            {
                "evidence": [
                    {
                        "evidence_id": " ",
                        "source_id": "src",
                        "locator": " ",
                        "supports": ["claim-one"],
                    }
                ]
            }
        )
        issues: list[dict[str, object]] = []
        _validate_evidence(entity, {"src"}, issues)
        self.assertEqual(
            [item["code"] for item in issues],
            ["EVIDENCE_ID", "EVIDENCE_LOCATOR"],
        )
        entity.data["evidence"][0] = {
            "evidence_id": "ev-1",
            "source_id": "src",
            "locator": "p. 1",
            "supports": ["claim-one"],
            "verified_on": None,
        }
        issues = []
        _validate_evidence(entity, {"src"}, issues)
        self.assertEqual([item["code"] for item in issues], ["EVIDENCE_VERIFIED_ON_TYPE"])

    def test_relation_types_unknown_fields_and_targets_match_schema(self) -> None:
        entity = _entity(
            {
                "relations": [
                    {
                        "relation_type": "cites",
                        "target_id": 123,
                        "note": ["bad"],
                        "extra": "x",
                    }
                ]
            }
        )
        issues: list[dict[str, object]] = []
        _validate_relations(entity, {"123": _entity({"id": "123"})}, {"cites"}, issues)
        self.assertEqual(
            {item["code"] for item in issues},
            {"RELATION_FIELD_UNKNOWN", "RELATION_FIELD_TYPE", "RELATION_TARGET"},
        )

    def test_temporal_required_fields_types_and_unknowns_match_schema(self) -> None:
        entity = _entity(
            {
                "temporal": {
                    "applicable_from": "2025-01-01",
                    "applicable_to": "2025-12-31",
                    "rule_version": 123,
                    "extra": "x",
                }
            }
        )
        issues: list[dict[str, object]] = []
        _validate_dates(entity, dt.date(2026, 7, 15), issues)
        self.assertEqual(
            {item["code"] for item in issues},
            {
                "RULE_TEMPORAL_FIELD_UNKNOWN",
                "RULE_TEMPORAL_FIELD_MISSING",
                "RULE_TEMPORAL_VERSION",
            },
        )
        null_issues: list[dict[str, object]] = []
        _validate_dates(_entity({"temporal": None}), dt.date(2026, 7, 15), null_issues)
        self.assertEqual([item["code"] for item in null_issues], ["RULE_TEMPORAL_TYPE"])

    def test_explicit_null_lists_evidence_and_relations_fail_type_checks(self) -> None:
        entity = _entity({"aliases": None, "evidence": None, "relations": None})
        issues: list[dict[str, object]] = []
        _validate_list_of_strings(entity, "aliases", issues)
        _validate_evidence(entity, set(), issues)
        _validate_relations(entity, {}, {"cites"}, issues)
        self.assertEqual(
            [item["code"] for item in issues],
            ["FIELD_TYPE", "EVIDENCE_TYPE", "RELATIONS_TYPE"],
        )


class MetadataPolicyTests(unittest.TestCase):
    def test_supersession_policy_diagnoses_without_choosing_an_end_date(self) -> None:
        data = {
            "id": "case-old",
            "legal_status": "superseded",
            "effective_from": "2023-01-13",
            "effective_to": "9999-12-31",
            "superseded_by": "case-new",
            "superseded_date": "2025-08-14",
        }
        diagnostics = supersession_diagnostics(data, {"case-new": object()})
        self.assertEqual([item.code for item in diagnostics], ["SUPERSESSION_OPEN_ENDED"])
        self.assertEqual(diagnostics[0].severity, "medium")

    def test_supersession_alias_cannot_point_back_to_the_same_entity(self) -> None:
        current = _entity({"id": "case-old"})
        diagnostics = supersession_diagnostics(
            {"id": "case-old", "superseded_by": "case-old-alias"},
            {"case-old-alias": current},
        )
        self.assertEqual([item.code for item in diagnostics], ["SUPERSESSION_SELF_REFERENCE"])

    def test_evidence_chronology_only_compares_document_date_when_verified(self) -> None:
        data = {
            "status": "review",
            "ingestion_status": "linked",
            "last_verified": "2026-07-10",
            "last_checked": "2026-07-10",
            "evidence": [{"verified_on": "2026-07-11"}],
        }
        review_codes = [
            item.code
            for item in verification_timeline_diagnostics(
                data,
                dt.date(2026, 7, 15),
                source_entity=True,
            )
        ]
        self.assertNotIn("EVIDENCE_AFTER_LAST_VERIFIED", review_codes)
        data["status"] = "verified"
        verified_codes = [
            item.code
            for item in verification_timeline_diagnostics(
                data,
                dt.date(2026, 7, 15),
                source_entity=True,
            )
        ]
        self.assertEqual(verified_codes, ["EVIDENCE_AFTER_LAST_VERIFIED"])

    def test_authority_policy_preserves_composite_candidate_semantics(self) -> None:
        law = _entity({"authority_level": 1})
        case = _entity({"authority_level": 2})
        data = {
            "entity_type": "concept",
            "ingestion_status": "verified",
            "primary_authority": "근로기준법 및 대법원 전원합의체",
            "primary_authority_id": "case",
            "authority_ids": ["law", "case"],
            "authority_level": 1,
        }
        targets = {"law": law, "case": case}
        self.assertEqual(inferred_authority_levels(data, targets), {1, 2})
        self.assertEqual(authority_diagnostics(data, targets), ())


class RepositoryPhaseTwoTests(unittest.TestCase):
    def test_graph_preserves_local_claim_nodes_and_evidence_refs(self) -> None:
        graph = export_graph(ROOT)
        self.assertEqual(graph["schema_version"], GRAPH_SCHEMA_VERSION)
        self.assertEqual(graph["entity_schema_version"], "1.3")
        self.assertEqual(graph["parse_issues"], [])
        self.assertEqual(len({node["id"] for node in graph["nodes"]}), len(graph["nodes"]))
        claim_nodes = [node for node in graph["nodes"] if node.get("node_type") == "claim"]
        entities, _ = load_entities(ROOT)
        expected = sum(len(evidence_claim_ids(entity.data.get("evidence"))) for entity in entities)
        self.assertEqual(len(claim_nodes), expected)
        self.assertTrue(all(node["id"].startswith("claim:") and "#" in node["id"] for node in claim_nodes))
        claim_edges = [edge for edge in graph["edges"] if edge["claim_refs"]]
        self.assertTrue(claim_edges)
        self.assertTrue(all(edge["evidence_refs"] for edge in claim_edges))
        self.assertTrue(
            all(
                reference.startswith("evidence:")
                for edge in claim_edges
                for reference in edge["evidence_refs"]
            )
        )
        expected_links: set[tuple[str, str, str, str]] = set()
        for entity in entities:
            entity_id = str(entity.data.get("id", ""))
            for evidence in as_list(entity.data.get("evidence")):
                if not isinstance(evidence, dict):
                    continue
                evidence_ref = global_evidence_id(entity_id, str(evidence.get("evidence_id", "")))
                source_ref = global_source_id(str(evidence.get("source_id", "")))
                locator = str(evidence.get("locator", ""))
                for claim_id in as_list(evidence.get("supports")):
                    expected_links.add(
                        (
                            global_claim_id(entity_id, str(claim_id)),
                            source_ref,
                            evidence_ref,
                            locator,
                        )
                    )
        actual_links = {
            (
                edge["source"],
                edge["target"],
                link["evidence_ref"],
                link["locator"],
            )
            for edge in graph["edges"]
            if edge["relation_type"] == "supported_by" and edge["source"].startswith("claim:")
            for link in edge["evidence_links"]
        }
        self.assertEqual(actual_links, expected_links)

    def test_graph_reports_cross_namespace_node_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wiki = root / "wiki"
            wiki.mkdir()
            first = wiki / "one.md"
            first.write_text(
                """---
id: "one"
entity_type: "concept"
evidence:
  - evidence_id: "ev-1"
    source_id: "src"
    locator: "p. 1"
    supports:
      - "claim-one"
---
Text.
""",
                encoding="utf-8",
            )
            collision_id = global_claim_id("one", "claim-one")
            second = wiki / "collision.md"
            second.write_text(
                f"""---
id: "{collision_id}"
entity_type: "concept"
---
Collision.
""",
                encoding="utf-8",
            )
            graph = export_graph(root)
        self.assertIn(
            "GRAPH_NODE_ID_DUPLICATE",
            {item.get("code") for item in graph["parse_issues"]},
        )

    def test_graph_accepts_manifest_only_sources_and_rejects_empty_node_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wiki = root / "wiki"
            wiki.mkdir()
            (wiki / "one.md").write_text(
                """---
id: "one"
entity_type: "concept"
evidence:
  - evidence_id: "ev-1"
    source_id: "manifest-only"
    locator: "p. 1"
    supports:
      - "claim-one"
---
Text.
""",
                encoding="utf-8",
            )
            sources = root / "sources"
            sources.mkdir()
            (sources / "raw-manifest.jsonl").write_text(
                json.dumps({"source_id": "manifest-only"}) + "\n",
                encoding="utf-8",
            )
            graph = export_graph(root)
        self.assertEqual(graph["parse_issues"], [])
        self.assertIn("source:manifest-only", {node["id"] for node in graph["nodes"]})

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wiki = root / "wiki"
            wiki.mkdir()
            (wiki / "missing.md").write_text(
                """---
entity_type: "concept"
title: "Missing"
---
Missing.
""",
                encoding="utf-8",
            )
            graph = export_graph(root)
        self.assertIn(
            "GRAPH_NODE_ID_MISSING",
            {item.get("code") for item in graph["parse_issues"]},
        )

    def test_default_lint_keeps_anchor_rollout_nonblocking(self) -> None:
        report = lint_repository(ROOT, today=dt.date(2026, 7, 16), strict_v13=True)
        self.assertEqual(report["summary"]["by_severity"]["high"], 0)
        self.assertEqual(report["summary"]["by_severity"]["critical"], 0)
        self.assertNotIn("EVIDENCE_CLAIM_UNRESOLVED", {item["code"] for item in report["issues"]})
        strict = lint_repository(
            ROOT,
            today=dt.date(2026, 7, 16),
            strict_v13=True,
            require_claim_anchors=True,
        )
        unresolved = [issue for issue in strict["issues"] if issue["code"] == "EVIDENCE_CLAIM_UNRESOLVED"]
        entities, _ = load_entities(ROOT)
        expected_unresolved = sum(
            len(evidence_claim_ids(entity.data.get("evidence")))
            - len(
                {
                    claim_id
                    for claim_id in evidence_claim_ids(entity.data.get("evidence"))
                    if claim_id in resolved_claim_ids(entity.data, entity.body)
                }
            )
            for entity in entities
        )
        self.assertEqual(len(unresolved), expected_unresolved)


if __name__ == "__main__":
    unittest.main()
