from __future__ import annotations

import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from graph_contract import RELATED_FIELD_TYPES
from kg_common import (
    Entity,
    as_list,
    entity_lookup,
    load_entities,
    load_json,
    resolve_entity_ref,
    scalar_text,
    wiki_targets,
)
from lint_wiki import _validate_log_targets, _validate_qa_regression
from log_contract import LOG_ACTIONS
from qa_catalog import validate_qa_catalog
from review_policy import recommended_review_cycle, review_deadline_passed
from schema_contract import load_schema_contract


def _entity(entity_id: str, entity_type: str) -> Entity:
    return Entity(
        path=Path(f"{entity_id}.md"),
        relative_path=f"wiki/{entity_type}/{entity_id}.md",
        data={"id": entity_id, "entity_type": entity_type},
        body="",
    )


def _qa_record(**updates: object) -> dict[str, object]:
    record: dict[str, object] = {
        "id": "qa-test",
        "as_of": "2026-07-15",
        "question": "질문",
        "expected": "답변",
        "required_authority_ids": ["case-test"],
        "required_rule_ids": ["rule-test"],
        "forbidden_claims": ["금지 주장"],
    }
    record.update(updates)
    return record


class SchemaContractTests(unittest.TestCase):
    def test_schema_and_vocabulary_are_consistent(self) -> None:
        contract = load_schema_contract(ROOT)
        self.assertEqual(contract.schema_version, "1.3")
        self.assertEqual(contract.problems, ())
        self.assertIn("status", contract.required_fields)
        self.assertIn("source_availability", contract.required_by_entity_type["case"])
        self.assertIn("case_numbers", contract.string_list_fields)
        self.assertIn("", contract.controlled_fields["conflict_resolution"])
        self.assertIn("guide", contract.controlled_fields["entity_type"])


class RepositoryGraphContractTests(unittest.TestCase):
    def test_related_fields_resolve_to_the_declared_entity_type(self) -> None:
        entities, parse_issues = load_entities(ROOT)
        self.assertEqual(parse_issues, [])
        _, names = entity_lookup(entities)
        mismatches: list[str] = []
        for entity in entities:
            for field, expected_type in RELATED_FIELD_TYPES.items():
                for target in wiki_targets(entity.data.get(field)):
                    matches = resolve_entity_ref(target, names)
                    if len(matches) != 1:
                        continue
                    actual_type = scalar_text(matches[0].data.get("entity_type"))
                    if actual_type != expected_type:
                        mismatches.append(
                            f"{entity.relative_path}: {field} -> {target} ({actual_type})"
                        )
        self.assertEqual(mismatches, [])

    def test_frontmatter_and_global_id_aliases_are_in_sync(self) -> None:
        entities, _ = load_entities(ROOT)
        frontmatter_aliases = {
            scalar_text(alias): scalar_text(entity.data.get("id"))
            for entity in entities
            for alias in as_list(entity.data.get("id_aliases"))
            if scalar_text(alias)
        }
        global_aliases = load_json(ROOT / "schemas" / "id-aliases.json", {}).get(
            "aliases_to_canonical", {}
        )
        self.assertEqual(global_aliases, frontmatter_aliases)

    def test_log_action_vocabulary_includes_migrations_and_rejects_unknown_values(self) -> None:
        self.assertIn("MIGRATE", LOG_ACTIONS)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            log = root / "wiki" / "logs" / "2026-07.md"
            log.parent.mkdir(parents=True)
            log.write_text("- [2026-07-15]\n  Action: UNKNOWN\n", encoding="utf-8")
            issues: list[dict[str, object]] = []
            _validate_log_targets(root, {}, issues)
        self.assertEqual([item["code"] for item in issues], ["LOG_ACTION_INVALID"])


class QaCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rule = _entity("rule-test", "rule")
        self.case = _entity("case-test", "case")
        self.targets = {
            "rule-test": self.rule,
            "rule-alias": self.rule,
            "case-test": self.case,
        }

    def _validate_lines(self, lines: list[str]) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "qa.jsonl"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return validate_qa_catalog(path, self.targets)

    def test_accepts_aliases_and_valid_records(self) -> None:
        record = _qa_record(required_rule_ids=["rule-alias"])
        result = self._validate_lines([json.dumps(record, ensure_ascii=False)])
        self.assertEqual(result, {"rows": 1, "issues": []})

    def test_reports_type_date_list_and_reference_errors_without_crashing(self) -> None:
        invalid = _qa_record(
            as_of="2026-99-99",
            required_authority_ids="case-test",
            required_rule_ids=["case-test", "missing-rule"],
            forbidden_claims=[],
        )
        result = self._validate_lines(
            ["[]", json.dumps(invalid, ensure_ascii=False), "{not-json"]
        )
        codes = [item["code"] for item in result["issues"]]
        self.assertEqual(result["rows"], 3)
        self.assertEqual(
            codes,
            [
                "INVALID_RECORD_TYPE",
                "INVALID_AS_OF",
                "INVALID_ID_LIST",
                "REQUIRED_ID_NOT_RULE",
                "UNKNOWN_RULE_ID",
                "INVALID_FORBIDDEN_CLAIMS",
                "INVALID_JSON",
            ],
        )

    def test_lint_adapter_uses_the_shared_catalogue_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "tests" / "qa_regression.jsonl"
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps(_qa_record(as_of="bad-date"), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            issues: list[dict[str, object]] = []
            _validate_qa_regression(root, self.targets, issues)
        self.assertEqual([item["code"] for item in issues], ["QA_REGRESSION_DATE"])
        self.assertEqual(issues[0]["severity"], "high")


class ReviewPolicyTests(unittest.TestCase):
    def test_cycles_and_deadlines_share_one_policy(self) -> None:
        as_of = dt.date(2026, 7, 15)
        self.assertEqual(
            recommended_review_cycle("discussion", "최신 동향", {}, as_of),
            "monthly",
        )
        self.assertEqual(recommended_review_cycle("rule", "규칙", {}, as_of), "quarterly")
        self.assertEqual(recommended_review_cycle("guide", "실무 가이드", {}, as_of), "quarterly")
        self.assertFalse(review_deadline_passed(as_of - dt.timedelta(days=31), "monthly", as_of))
        self.assertTrue(review_deadline_passed(as_of - dt.timedelta(days=32), "monthly", as_of))
        self.assertFalse(review_deadline_passed(as_of - dt.timedelta(days=999), "unknown", as_of))


if __name__ == "__main__":
    unittest.main()
