---
schema_version: "1.3"
id: "rule-inclusive-wage-types-fixed-overtime"
id_aliases: []
entity_type: "rule"
title: "정액급제·정액수당제·고정OT 구분 규칙"
aliases: []
jurisdiction: "KR"
status: "verified"
legal_status: "current"
ingestion_status: "verified"
primary_authority: "대법원 2022. 2. 10. 선고 2018다298904 판결"
primary_authority_id: "case-2018다298904"
authority_ids:
  - "case-2018다298904"
  - "case-2020다300299"
  - "interpretation-moel-inclusive-wage-guideline-2026-04-09"
authority_level: 3
enforcement_weight: "high"
conflict_status: "active"
conflict_type: "interpretive"
conflict_resolution: "unresolvable"
conflict_resolution_note: "판례상 정액급·정액수당 포괄임금 유형과 2026년 고용노동부가 구분 산정·시정 대상으로 제시한 행정상 분류를 함께 적용한다. 법령 또는 판례·지침 변경 전까지 두 기준을 병기한다."
conflict_resolved_date: ""
effective_from: "2022-02-10"
effective_to: "9999-12-31"
as_of_date: "2026-07-21"
superseded_by: ""
superseded_date: ""
review_cycle: "quarterly"
review_trigger:
  - "포괄임금 유형 또는 고정OT 관련 판례·행정지침 변경"
related_concepts:
  - "[[포괄임금약정]]"
  - "[[고정OT 약정]]"
related_rules:
  - "[[포괄임금약정 성립 판단 규칙]]"
  - "[[포괄임금 최저임금 비교대상 시급 산정 규칙]]"
related_cases:
  - "[[대법원 2022. 2. 10. 선고 2018다298904 판결]]"
  - "[[대법원 2024. 12. 26. 선고 2020다300299 판결]]"
related_laws:
  - "[[근로기준법 제17조 근로조건의 명시]]"
  - "[[근로기준법 제56조 연장 야간 및 휴일 근로]]"
related_interpretations:
  - "[[고용노동부 2026. 4. 9. 포괄임금 오남용 방지 지도 지침]]"
related_fact_patterns:
  - "[[기본급과 법정수당이 구분되지 않은 정액급제]]"
  - "[[실근로시간보다 적은 고정OT 지급]]"
related_raw:
  - "[[raw/cases/대법원 2022. 2. 10. 선고 2018다298904 판결.pdf]]"
  - "[[raw/interpretations/공짜노동 근절을 위한 포괄임금 오남용 방지 지도지침.pdf]]"
source_urls:
  - "https://www.scourt.go.kr/supreme/news/NewsViewAction2.work?gubun=4&searchOption=000100&searchWord=&seqnum=8240"
  - "https://www.moel.go.kr/news/enews/report/enewsView.do?news_seq=19208"
source_excerpt:
  - "기본임금의 분리 여부, 법정수당의 특정 여부와 실제 정산 구조로 유형을 구분"
evidence:
  - evidence_id: "ev-rule-inclusive-types"
    source_id: "raw-case-2018da298904"
    locator: "PDF pp.2-4, 이유 1-3"
    excerpt: "포괄임금의 유형을 정의하고 실제 임금 산식과 수당별 지급 범위로 약정을 분류한다."
    supports:
      - "claim-rule-inclusive-types"
      - "claim-rule-inclusive-types-effects"
    verified_on: "2026-07-21"
  - evidence_id: "ev-rule-fixed-ot-type"
    source_id: "raw-interpretation-moel-inclusive-wage-guideline-2026-04"
    locator: "PDF pp.2-3, 기본원칙"
    excerpt: "고정OT를 예정시간분 수당 지급과 실근로시간 차액 정산 구조로 설명한다."
    supports:
      - "claim-rule-fixed-ot-type"
      - "claim-rule-inclusive-types-administration"
    verified_on: "2026-07-21"
relations:
  - relation_type: "cites"
    target_id: "case-2018다298904"
    target: "[[대법원 2022. 2. 10. 선고 2018다298904 판결]]"
    note: "포괄임금의 두 유형과 수당별 범위를 제시한다."
  - relation_type: "interprets"
    target_id: "interpretation-moel-inclusive-wage-guideline-2026-04-09"
    target: "[[고용노동부 2026. 4. 9. 포괄임금 오남용 방지 지도 지침]]"
    note: "감독 실무상 고정OT 구분을 반영한다."
  - relation_type: "conflicts_with"
    target_id: "interpretation-moel-inclusive-wage-guideline-2026-04-09"
    target: "[[고용노동부 2026. 4. 9. 포괄임금 오남용 방지 지도 지침]]"
    note: "판례상 계약 유형과 행정상 시정 대상 분류 사이의 해석상 긴장을 표시한다."
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
rule_type: "calculation"
issue: "정액 임금 구조를 정액급제·정액수당제·고정OT 중 무엇으로 분류할지"
elements:
  - "기본임금이 별도로 정해졌는지"
  - "법정수당이 항목별 정액으로 특정되었는지"
  - "예정시간과 실근로시간의 차액을 정산하는지"
exceptions: []
conclusion: "명칭이 아니라 임금 항목, 산식, 예정시간과 실제 정산 구조로 유형을 정한다."
temporal:
  applicable_from: "2022-02-10"
  applicable_to: "9999-12-31"
  rule_version: "2018다298904 판결 및 2026년 고용노동부 지침"
  transition_note: "행정지침이 판례상 정액수당형과 실무상 고정OT를 정산 여부로 세분한다."
law_version: "근로기준법 제17조·제56조 현행"
law_revision_date: "2024-10-22"
wage_criteria: []
decision_factors:
  - "총액에서 기본임금과 법정수당을 분리할 수 있는지"
  - "수당 명목마다 예정시간이 기재되어 있는지"
  - "실제 초과근로가 예정시간을 넘을 때 추가 지급하는지"
wage_type:
  - "임금"
worker_scope: "정액 임금 또는 고정 시간외수당을 지급받는 근로자"
calculation_unit: "임금지급기별 임금 구조"
extinction_period: "3년"
---
# 정액급제·정액수당제·고정OT 구분 규칙

## Issue

‘포괄임금’ 또는 ‘고정OT’라는 명칭을 실제 법률상 임금 구조로 어떻게 분류할 것인가.

## Rule

기본임금의 분리 여부, 법정수당 항목과 예정시간의 특정 여부, 실근로시간 초과분의 정산 여부를 확인해 정액급제·정액수당제·고정OT를 구분한다. ^claim-rule-inclusive-types

이 세 표현은 동일한 법원에서 나온 동렬의 법정 분류가 아니다. 대법원은 포괄임금약정을 정액급형과 정액수당형으로 구분하고, 고용노동부는 수당별 예정시간과 금액을 특정하고 차액을 정산하는 약정을 실무상 고정OT로 구별한다.

## 구조적 위치

| 상위 구조 | 하위 유형 | 핵심 특징 |
|---|---|---|
| 판례상 포괄임금약정 | 정액급형 | 기본임금과 법정수당을 분리하지 않고 월급·일당 총액만 정함 |
| 판례상 포괄임금약정 | 정액수당형 | 기본임금은 정하되 일부 법정수당을 시간 수와 무관한 정액으로 포괄함 |
| 행정·실무상 구별되는 정액 약정 | 고정OT | 수당별 예정시간·금액을 특정하고 실제 법정수당이 더 많으면 차액을 정산함 |

고정OT가 계약서에 쓰인 명칭이라는 이유만으로 자동 분류하지 않는다. 정액수당형과 고정OT의 경계는 수당별 시간·산식이 특정되고 실제 초과분을 계속 정산했는지에 따라 판단한다.

## Elements

| 확인 질문 | 예 | 분류 방향 |
|---|---|---|
| 기본임금이 별도로 확정되어 있는가 | 아니오 | 정액급형 검토 |
| 총액에서 기본임금과 법정수당을 역산해야 하는가 | 예 | 정액급형 검토 |
| 기본임금은 있으나 여러 법정수당을 하나의 정액으로 묶었는가 | 예 | 정액수당형 검토 |
| 연장·야간·휴일수당별 예정시간과 금액이 있는가 | 예 | 고정OT 검토 |
| 실제 법정수당이 약정액보다 많을 때 차액을 지급하는가 | 예 | 고정OT에 가까움 |
| 초과분을 지급하지 않고 정액으로 종결하는가 | 예 | 정액수당형 또는 무효·체불 문제 검토 |

고정OT에서는 실제 법정수당이 약정액보다 많으면 차액을 지급하고, 실제 법정수당이 적으면 약정한 금액을 지급한다. ^claim-rule-fixed-ot-type

## Exceptions

계약상 명칭과 실제 지급 구조가 다르면 실제 산식과 정산 관행을 우선한다.

## Conclusion

분류 결과는 성립 범위, 법정수당 차액, 최저임금 비교대상 시급 산식과 임금대장·명세서 시정방식에 직접 영향을 준다. 정액급형은 총액 역산이 필요하고, 정액수당형은 기본임금과 포괄된 수당 범위를 확인하며, 고정OT는 수당별 예정시간과 실근로시간을 비교한다. ^claim-rule-inclusive-types-effects

## Authority

- [[대법원 2022. 2. 10. 선고 2018다298904 판결]]
- [[고용노동부 2026. 4. 9. 포괄임금 오남용 방지 지도 지침]]

## Application

‘연장근로수당 월 20시간분’의 금액과 산식이 명시되어 있고 초과시간을 추가 정산하면 고정OT에 가깝다. 기본급과 수당 구분 없이 월 300만 원만 정했다면 정액급형을 검토한다. 기본급 250만 원과 ‘시간외수당 50만 원’만 정하고 연장·야간·휴일을 구분하지 않거나 초과분을 정산하지 않는다면 정액수당형 및 법정수당 체불 문제를 검토한다.

2026년 고용노동부 지침은 정액급형과 법정수당을 구분하지 않은 정액수당형을 임금대장·명세서에 맞게 구분·산정하도록 시정하는 감독기준을 제시한다. 따라서 판례상 유형 분류 결과만으로 현행 감독상 적법성을 확정해서는 안 된다. ^claim-rule-inclusive-types-administration

## Notes

분류와 성립은 별개의 질문이다. 외형상 정액급형에 해당하더라도 법정수당을 포함한다는 합의가 인정되지 않을 수 있고, 고정OT 형식을 갖추어도 실제 초과분을 지급하지 않으면 체불이 발생할 수 있다.
