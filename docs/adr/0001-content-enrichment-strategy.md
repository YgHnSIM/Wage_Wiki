# 0001. 지식 그래프 내용 충실화 및 품질 무결성 전략

Wage_Wiki 지식 그래프의 내용 충실화(Content Enrichment)를 위한 수집·정규화·검증·배포의 단계별 통합 전략을 정의합니다.

## 맥락 및 결정 (Context & Decision)

Wage_Wiki는 190개의 정규화 지식 엔티티와 v1.4 스키마 검증 기준 결함 0건(Clean Baseline)을 유지하고 있습니다. 지식 보강 과정에서 데이터 정밀도와 실무 유용성을 동시에 극대화하기 위해 다음과 같이 결정했습니다:

1. **단계적 통합 (Staged Integration)**: `raw/` 원시 사료(판례, 행정해석, 언론/연구자료)의 지식화율(Coverage)을 100% 정규화(Phase 1)한 후, 5인 미만 특례, 부당해고 등 신규 법률 영역으로 확장(Phase 2)합니다.
2. **4원 결합 검증 (4-way Triad)**: 지식 엔티티 추가 시 `wiki/` 엔티티, `claim:`/`evidence:` 앵커, `fact_pattern`(구체적 사실관계 시나리오), `tests/qa_regression.jsonl`(자동화 검증)을 동시 연계 구축합니다.
3. **단일상 엄격 검증 (Strict Single-pass)**: 초안 상태의 미검증 데이터 수용을 지양하고, v1.4 스키마 준수를 작성 시점부터 강제합니다.
4. **배포 및 시각화 고도화**: 지식 보강과 연동하여 static site의 Mermaid 관계망 시각화, FTS 검색 인덱스, 대시보드 통계를 동시 업데이트합니다.
