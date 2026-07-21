---
schema_version: "1.3"
id: "fact-pattern-fixed-overtime-shortfall"
id_aliases: []
entity_type: "fact_pattern"
title: "실근로시간보다 적은 고정OT 지급"
aliases: []
jurisdiction: "KR"
status: "verified"
legal_status: "current"
ingestion_status: "verified"
primary_authority: "고용노동부 2026. 4. 9. 포괄임금 오남용 방지 지도 지침"
primary_authority_id: "interpretation-moel-inclusive-wage-guideline-2026-04-09"
authority_ids:
  - "case-2008다6052"
  - "interpretation-moel-inclusive-wage-guideline-2026-04-09"
authority_level: 5
enforcement_weight: "medium"
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
  - "포괄임금 지도지침 또는 법정수당 판례 변경"
related_concepts:
  - "[[고정OT 약정]]"
related_rules:
  - "[[포괄임금약정 유효성과 법정수당 차액 지급 규칙]]"
  - "[[포괄임금의 임금대장·명세서 및 실근로시간 정산 규칙]]"
related_cases:
  - "[[대법원 2010. 5. 13. 선고 2008다6052 판결]]"
related_laws:
  - "[[근로기준법 제48조 임금대장 및 임금명세서]]"
  - "[[근로기준법 제56조 연장 야간 및 휴일 근로]]"
related_interpretations:
  - "[[고용노동부 2026. 4. 9. 포괄임금 오남용 방지 지도 지침]]"
related_fact_patterns: []
related_raw:
  - "[[raw/interpretations/공짜노동 근절을 위한 포괄임금 오남용 방지 지도지침.pdf]]"
source_urls:
  - "https://www.moel.go.kr/news/enews/report/enewsView.do?news_seq=19208"
source_excerpt:
  - "약정한 고정OT보다 실제 법정수당이 많으면 차액 지급"
evidence:
  - evidence_id: "ev-fact-fixed-ot-shortfall"
    source_id: "raw-interpretation-moel-inclusive-wage-guideline-2026-04"
    locator: "PDF pp.2-6, 기본원칙 및 지도기준"
    excerpt: "고정OT 예정시간보다 실제 연장·야간·휴일근로가 많으면 법정수당 차액을 지급하도록 한다."
    supports:
      - "claim-fact-fixed-ot"
      - "claim-fact-fixed-ot-application"
    verified_on: "2026-07-21"
relations:
  - relation_type: "applies"
    target_id: "rule-inclusive-wage-recording-reconciliation"
    target: "[[포괄임금의 임금대장·명세서 및 실근로시간 정산 규칙]]"
    note: "매월 실근로시간과 고정OT 예정시간을 대조한다."
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
# 실근로시간보다 적은 고정OT 지급

## Facts

근로계약은 월 20시간분의 연장근로수당을 고정OT로 정했지만, 출퇴근기록상 실제 연장근로는 월 35시간이다. 임금명세서에는 고정OT 금액만 있고 초과 15시간분 정산이 없다. ^claim-fact-fixed-ot

## Rule Application

통상임금과 제56조 가산율로 35시간분 법정수당을 계산한 뒤 이미 지급한 20시간분 상당액을 공제하여 차액을 산정한다. 임금대장·명세서에는 실제 시간과 계산방법을 반영한다. ^claim-fact-fixed-ot-application

## Conclusion

고정OT 약정 자체와 별개로 법정수당 미달 차액을 지급해야 한다.
