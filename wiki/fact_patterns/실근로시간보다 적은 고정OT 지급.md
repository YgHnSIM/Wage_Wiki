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
      - "claim-fact-fixed-ot-example"
      - "claim-fact-fixed-ot-lower"
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

1. 고정OT가 연장·야간·휴일 중 어느 수당을 몇 시간분 지급하는 것인지 확인한다.
2. 출퇴근기록 등으로 수당별 실제 근로시간을 확정한다.
3. 통상임금과 제56조의 수당별 가산율로 실제 법정수당을 계산한다.
4. 지급 목적이 같은 고정OT 금액을 대응되는 법정수당에서 공제하고 부족분을 지급한다.
5. 임금대장에는 실제 연장·야간·휴일근로시간과 항목별 금액을, 임금명세서에는 계산방법을 반영한다. ^claim-fact-fixed-ot-application

### 단순 계산 예시

통상시급이 15,000원이고 고정OT가 순수 연장근로 20시간분이라면 약정액은 450,000원이다. 실제 연장근로가 35시간이면 법정수당은 787,500원이므로 337,500원을 추가 지급한다. ^claim-fact-fixed-ot-example

```text
고정OT = 15,000원 × 20시간 × 1.5 = 450,000원
실제 법정수당 = 15,000원 × 35시간 × 1.5 = 787,500원
추가 지급액 = 787,500원 - 450,000원 = 337,500원
```

야간근로 또는 휴일근로가 겹치면 시간과 가산부분을 각각 분리해 계산한다. 고정OT가 ‘연장수당’ 명목인데 야간수당까지 지급한 것으로 공제하려면 약정 문언과 지급 목적이 그 수당까지 포함하는지 별도로 확인해야 한다.

### 실제 근로가 예정시간보다 적은 경우

예를 들어 실제 연장근로가 12시간뿐이더라도 20시간분 고정OT로 약정했다면 2026년 지침은 약정액 450,000원을 그대로 지급하는 것으로 본다. 실제 수당이 적다는 이유로 매월 약정액을 임의 감액하면 고정OT라는 임금 약정과도 맞지 않는다. ^claim-fact-fixed-ot-lower

## Conclusion

고정OT는 실제 근로시간을 20시간으로 간주하는 제도가 아니다. 실제 법정수당이 약정액을 넘는 달에는 차액을 지급하고, 적은 달에는 약정 고정액을 지급하며, 이 결과를 임금대장과 명세서에서 확인할 수 있어야 한다.
