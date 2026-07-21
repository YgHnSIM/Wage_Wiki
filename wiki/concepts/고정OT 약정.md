---
schema_version: "1.3"
id: "concept-fixed-overtime-agreement"
id_aliases: []
entity_type: "concept"
title: "고정OT 약정"
aliases:
  - "고정 연장근로수당 약정"
  - "정액 법정수당 약정"
jurisdiction: "KR"
status: "verified"
legal_status: "current"
ingestion_status: "verified"
primary_authority: "고용노동부 2026. 4. 9. 포괄임금 오남용 방지 지도 지침"
primary_authority_id: "interpretation-moel-inclusive-wage-guideline-2026-04-09"
authority_ids:
  - "case-2018다298904"
  - "interpretation-moel-inclusive-wage-guideline-2026-04-09"
authority_level: 5
enforcement_weight: "high"
conflict_status: "none"
conflict_type: "none"
conflict_resolution: ""
conflict_resolution_note: ""
conflict_resolved_date: ""
effective_from: "2026-04-09"
effective_to: "9999-12-31"
as_of_date: "2026-07-21"
superseded_by: ""
superseded_date: ""
review_cycle: "quarterly"
review_trigger:
  - "고용노동부 포괄임금 지도지침 개정"
related_concepts:
  - "[[포괄임금약정]]"
related_rules:
  - "[[정액급제·정액수당제·고정OT 구분 규칙]]"
  - "[[포괄임금의 임금대장·명세서 및 실근로시간 정산 규칙]]"
related_cases:
  - "[[대법원 2022. 2. 10. 선고 2018다298904 판결]]"
related_laws:
  - "[[근로기준법 제48조 임금대장 및 임금명세서]]"
  - "[[근로기준법 제56조 연장 야간 및 휴일 근로]]"
related_interpretations:
  - "[[고용노동부 2026. 4. 9. 포괄임금 오남용 방지 지도 지침]]"
related_fact_patterns:
  - "[[실근로시간보다 적은 고정OT 지급]]"
related_raw:
  - "[[raw/interpretations/공짜노동 근절을 위한 포괄임금 오남용 방지 지도지침.pdf]]"
source_urls:
  - "https://www.moel.go.kr/news/enews/report/enewsView.do?news_seq=19208"
source_excerpt:
  - "일정 시간을 정하여 법정수당을 정액으로 지급하고 실제 근로시간과 정산하는 약정"
evidence:
  - evidence_id: "ev-concept-fixed-ot-definition"
    source_id: "raw-interpretation-moel-inclusive-wage-guideline-2026-04"
    locator: "PDF pp.2-3, 포괄임금 기본원칙"
    excerpt: "고정OT 약정은 일정 시간분의 법정수당을 정액 지급하되 실근로시간 기준 정산이 필요한 구조이다."
    supports:
      - "claim-concept-fixed-ot-definition"
      - "claim-concept-fixed-ot-settlement"
      - "claim-concept-fixed-ot-recording"
    verified_on: "2026-07-21"
relations:
  - relation_type: "interprets"
    target_id: "interpretation-moel-inclusive-wage-guideline-2026-04-09"
    target: "[[고용노동부 2026. 4. 9. 포괄임금 오남용 방지 지도 지침]]"
    note: "행정지침이 감독상 고정OT 구분과 정산 기준을 제시한다."
last_checked: "2026-07-21"
last_verified: "2026-07-21"
last_updated: "2026-07-21"
verified_by:
  - "codex-official-source-review"
verification:
  verifier_ids:
    - "codex"
  methods:
    - "official_source_review"
  note: ""
---
# 고정OT 약정

## Definition

고정OT 약정은 일정한 연장·야간·휴일근로 시간분의 법정수당을 미리 정액으로 지급하되, 실제 근로시간에 따라 산출한 법정수당이 그 정액보다 많으면 차액을 추가 지급하는 임금 약정이다. ^claim-concept-fixed-ot-definition

## 성립 구조

고정OT로 운영하려면 적어도 다음 내용을 계약·임금규정과 실제 지급자료에서 확인할 수 있어야 한다.

- 포함하는 수당이 연장·야간·휴일근로수당 중 무엇인지
- 수당별 예정시간과 금액이 얼마인지
- 통상임금과 가산율을 반영한 계산방법이 무엇인지
- 예정시간을 넘은 실제 근로의 차액을 언제 어떻게 정산하는지

‘시간외수당 30만 원’처럼 수당의 종류·시간·산식을 알 수 없는 표기는 고정OT라는 이름만으로 명확한 약정이 되지 않는다.

## 포괄임금약정과의 관계

판례상 정액수당형 포괄임금약정은 법정수당을 실제 근로시간 수와 무관한 정액으로 정하는 구조이다. 고정OT는 수당별 예정시간을 특정하고 실제 근로시간과 비교하여 초과분을 정산한다는 점에서 이를 구별한다. 다만 고정OT는 법률이 정의한 독립 유형이 아니므로 실제 구조가 정액수당형인지 고정OT인지 [[정액급제·정액수당제·고정OT 구분 규칙]]으로 판단한다.

## 실근로시간과의 정산

| 비교 결과 | 지급 원칙 |
|---|---|
| 실제 법정수당이 약정액보다 큼 | 약정액에 미달 차액을 더하여 지급 |
| 실제 법정수당이 약정액과 같음 | 약정액 지급으로 해당 기간 수당 충족 |
| 실제 법정수당이 약정액보다 작음 | 약정한 고정액을 그대로 지급 |

따라서 고정OT는 예정시간을 실제 근로시간으로 간주하는 제도가 아니다. 실제 연장·야간·휴일근로시간을 수당별로 산정하고, 법정수당과 약정액을 임금지급기마다 비교해야 한다. ^claim-concept-fixed-ot-settlement

## 기록과 명세

임금대장에는 실제 근로시간수와 연장·야간·휴일근로 시간수 및 임금 항목별 금액을 기록하고, 임금명세서에는 고정OT 금액과 시간에 따른 계산방법을 표시한다. 근로시간수 기재 예외가 적용되는 근로자라도 임금 항목별 금액과 지급근거까지 생략할 수 있는 것은 아니다. ^claim-concept-fixed-ot-recording

## Rule Links

[[정액급제·정액수당제·고정OT 구분 규칙]]으로 약정 구조를 분류하고, [[포괄임금의 임금대장·명세서 및 실근로시간 정산 규칙]]으로 기록과 차액 정산을 확인한다.

## Notes

고정OT 약정은 연장근로의 사전 승인절차나 제53조상 연장근로 한도를 대신하지 않는다. 약정시간을 초과한 근로가 승인되지 않았다는 이유만으로 사용자의 지휘·묵인 아래 이루어진 실제 근로의 수당 문제가 당연히 사라지는 것도 아니다.
