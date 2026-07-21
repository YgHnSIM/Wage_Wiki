from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from check_commit_messages import CommitRecord, allowed_scopes, load_policy, validate_record


POLICY = load_policy(ROOT / "schemas" / "commit-message-v1.json")


class CommitMessagePolicyTests(unittest.TestCase):
    def codes(self, record: CommitRecord) -> list[str]:
        return [issue["code"] for issue in validate_record(record, POLICY)]

    def test_policy_has_distinct_entity_topic_and_system_scopes(self) -> None:
        self.assertEqual(POLICY["history_mode"], "all")
        self.assertIn("concept", POLICY["scope_groups"]["entity"])
        self.assertIn("performance-pay", POLICY["scope_groups"]["legal-topic"])
        self.assertIn("validation", POLICY["scope_groups"]["system"])
        self.assertIn("validation", allowed_scopes(POLICY, "refactor"))
        self.assertNotIn("research", {
            scope
            for values in POLICY["scope_groups"].values()
            for scope in values
        })

    def test_accepts_valid_knowledge_and_system_subjects(self) -> None:
        subjects = [
            "create(concept): 노동관행의 규범적 효력 문서 생성",
            "fix(concept): 고정성 적용 종료일 정정",
            "refactor(validation): 데이터·스키마 검증 계약 통합",
            "style(site): 데스크톱 헤더와 문서 그리드 정렬",
        ]
        for subject in subjects:
            with self.subTest(subject=subject):
                self.assertEqual(self.codes(CommitRecord("test", subject)), [])

    def test_rejects_missing_scope_unknown_type_and_wrong_type_scope_pair(self) -> None:
        self.assertIn(
            "COMMIT_SUBJECT_FORMAT",
            self.codes(CommitRecord("test", "docs: 노동관행 문서 추가")),
        )
        self.assertIn(
            "COMMIT_TYPE_UNKNOWN",
            self.codes(CommitRecord("test", "change(repo): 문서 구조 변경")),
        )
        self.assertIn(
            "COMMIT_TYPE_SCOPE_MISMATCH",
            self.codes(CommitRecord("test", "docs(concept): 노동관행 문서 생성")),
        )
        self.assertIn(
            "COMMIT_TYPE_SCOPE_MISMATCH",
            self.codes(CommitRecord("test", "ingest(raw): 최저임금안 편입")),
        )

    def test_rejects_english_generic_and_terminal_summary(self) -> None:
        self.assertIn(
            "COMMIT_SUMMARY_KOREAN",
            self.codes(CommitRecord("test", "style(site): align desktop header")),
        )
        self.assertIn(
            "COMMIT_SUMMARY_GENERIC",
            self.codes(CommitRecord("test", "update(concept): 고정성 문서 업데이트")),
        )
        self.assertIn(
            "COMMIT_SUMMARY_TERMINAL",
            self.codes(CommitRecord("test", "fix(site): 문서 목차 정렬.")),
        )

    def test_requires_structured_body_for_ingest_raw_schema_and_large_commits(self) -> None:
        self.assertIn(
            "COMMIT_BODY_REQUIRED",
            self.codes(CommitRecord("test", "ingest(wage-arrears): 임금체불 판결 편입")),
        )
        self.assertIn(
            "COMMIT_BODY_REQUIRED",
            self.codes(
                CommitRecord(
                    "test",
                    "docs(agent): 커밋 메시지 규칙 변경",
                    changed_files=("schemas/commit-message-v1.json",),
                )
            ),
        )
        self.assertIn(
            "COMMIT_BODY_REQUIRED",
            self.codes(
                CommitRecord(
                    "test",
                    "fix(repo): 저장소 파일 정리",
                    changed_files=tuple(f"path/{index}" for index in range(10)),
                )
            ),
        )

    def test_accepts_required_body_sections_on_same_line_or_following_lines(self) -> None:
        message = """ingest(performance-pay): 경영성과급 판례리뷰 편입

Source: 판례리뷰 원문

Changes:
- raw와 관련 엔티티 반영

Verify: strict lint 통과
"""
        self.assertEqual(
            self.codes(
                CommitRecord(
                    "test",
                    message,
                    changed_files=("raw/research_press/review.pdf",),
                )
            ),
            [],
        )

    def test_skips_generated_merge_commits(self) -> None:
        record = CommitRecord(
            "merge",
            "Merge pull request #1 from example/topic",
            is_merge=True,
        )
        self.assertEqual(self.codes(record), [])


if __name__ == "__main__":
    unittest.main()
