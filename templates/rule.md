---
schema_version: "1.3"
id: "rule-"
id_aliases: []
entity_type: rule
title: ""
aliases: []
jurisdiction: KR
status: draft
legal_status: current
ingestion_status: imported
primary_authority: ""
primary_authority_id: ""
authority_ids:
  - "AUTHORITY_ID"
authority_level: 7
enforcement_weight: low
conflict_status: none
conflict_type: none
conflict_resolution: ""
conflict_resolution_note: ""
conflict_resolved_date: ""
effective_from: 1900-01-01
effective_to: 9999-12-31
as_of_date: "{{date}}"
superseded_by: ""
superseded_date: ""
review_cycle: quarterly
review_trigger: []
related_concepts: []
related_rules: []
related_cases:
  - "[[CASE_DOCUMENT]]"
related_laws:
  - "[[LAW_DOCUMENT]]"
related_interpretations: []
related_fact_patterns: []
related_raw:
  - "[[raw/RAW_DOCUMENT]]"
source_urls: []
source_excerpt: []
evidence:
  - evidence_id: "ev-rule-001"
    source_id: "raw-"
    locator: ""
    excerpt: ""
    supports:
      - "rule-claim-001"
    verified_on: ""
relations:
  - relation_type: cites
    target_id: "AUTHORITY_ID"
    target: "[[AUTHORITY_DOCUMENT]]"
    note: ""
last_checked: ""
last_verified: ""
last_updated: "{{date}}"
verified_by: []
verification:
  verifier_ids: []
  methods: []
  note: ""
rule_type: inclusion
issue: ""
elements: []
exceptions: []
conclusion: ""
temporal:
  applicable_from: 1900-01-01
  applicable_to: 9999-12-31
  rule_version: ""
  transition_note: ""
law_version: ""
law_revision_date: ""
wage_criteria: []
decision_factors: []
wage_type: []
worker_scope: ""
calculation_unit: ""
extinction_period: ""
---

# {{title}}

> [!warning] 적용 전 확인
> 이 Rule의 법령 버전, 적용기간, 권위 수준과 `status`를 확인한다.

## Issue

판정해야 하는 법적 질문과 다른 영역에서 독립적으로 다시 판단해야 하는 질문을 구분한다.

## Rule

요건·예외·결론을 한 문단으로 제시한다. ^rule-claim-001

## Elements

각 요소마다 필요한 사실과 증빙을 대응시킨다.

## Exceptions

원칙과 다른 결론을 만드는 예외·경계사례를 적는다.

## 판정 알고리즘

1. 사실관계와 적용시점을 확정한다.
2. 산입·제외 요건을 순서대로 적용한다.
3. 산정 기초를 확정한다.
4. 한도·요율·상하한과 부담주체를 적용한다.
5. 반대 사실과 누락 증빙을 기록한다.

## Conclusion

## Authority

직접 권위와 보조적·설득적 자료를 구분하고, 판례가 직접 판단하지 않은 영역을 명시한다.

## Application

### 정례

### 반례·경계사례

### 수치 가상례

기준일, 가정, 공식, 반올림과 신고 귀속시점을 표시한다.

## 신고·대사

- 급여대장:
- 원천세:
- 국민연금·건강보험:
- 고용·산재보험:
- 회계·증빙:

## Notes

법령·요율 변경, 권위 충돌, 미검증 쟁점과 재검토 트리거를 적는다.

