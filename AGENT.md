# AGENT.md

대한민국 임금법 Legal Knowledge Graph 운영 규약

---

## 1. Mission

본 저장소는 대한민국 임금법 영역의 법률 지식 그래프(Legal Knowledge Graph)를 구축하기 위한 저장소이다.

LLM은 다음 목표를 따른다.

1. 원본 자료의 무결성 보존
2. 법적 권위에 따른 지식 정제
3. 최신성 유지
4. 추론 가능한 법률 지식 네트워크 구축
5. 변경 이력의 완전한 추적성 확보
6. Rule 중심 법률 모델링 수행
7. GraphRAG 및 법률 QA에 적합한 구조 유지

---

## 2. Immutable Principles

### 2.1 Raw First

모든 지식의 출발점은 `/raw/` 이다.

LLM은 다음 행위를 절대 금지한다.

- raw 문서 수정
- raw 문서 삭제
- raw 문서 재작성
- raw 문서 요약본으로 대체

원본은 타임스탬프와 함께 영구 보존한다.

---

### 2.1.1 Raw Auto Routing

`/raw/` 루트에 새 파일이 직접 추가된 경우, LLM은 추출 작업을 시작하기 전에 해당 파일을 적절한 raw 하위 폴더로 자동 이동한다.

이동은 **파일 내용 변경이 아니라 보존 경로 정리**로 본다. 단, 다음 조건을 반드시 지킨다.

- 파일 바이트를 수정하지 않는다.
- 기존 파일을 덮어쓰지 않는다.
- 동일 파일명이 이미 있으면 파일명 끝에 `__YYYYMMDD-HHMMSS`를 붙여 충돌을 피한다.
- 이동 전후 경로를 Log에 `ROUTE_RAW` 액션으로 기록한다.
- 이후 `related_raw`, `Source`, `Target`에는 이동 후 최종 raw 경로를 사용한다.

자동 분류 기준은 다음 순서를 따른다.

| 대상 폴더 | 분류 기준 |
|----------|----------|
| `/raw/laws/` | 법률, 시행령, 시행규칙, 조문, 법령 개정문 |
| `/raw/cases/` | 판결문, 결정문, 사건번호, 법원명, 선고일이 확인되는 자료 |
| `/raw/interpretations/` | 고용노동부 행정해석, 질의회시, 예규, 지침 |
| `/raw/company_norms/` | 취업규칙, 단체협약, 임금규정, 사규, 근로계약 양식 |
| `/raw/research_press/` | 논문, 연구보고서, 보도자료, 기사, 해설 자료 |
| `/raw/_triage/` | 위 기준으로 확정 분류할 수 없는 자료 |

`/raw/_triage/`로 이동한 자료는 entity 생성을 보류하고, 필요한 경우 사용자에게 분류 판단을 요청한다.

---

### 2.2 Atomic Editing

하나의 파일은 하나의 역할만 수행한다.

**금지:**

- 개념 + 판례 + 법령 혼합
- 법리 + 연혁 + 학설 혼합
- 대형 백과사전식 문서 생성

**허용 단위 (entity_type 참조):**

- Concept
- Rule
- Case
- Law
- History
- Discussion
- Fact Pattern

---

### 2.3 Query Driven Dashboard

`index.md` 및 각 폴더 Dashboard는 수동 편집을 금지한다.

Dataview 및 자동 Query만 사용한다.

---

## 3. Knowledge Modeling Philosophy

본 저장소는 Document-Oriented Wiki가 아닌 **Rule-Oriented Legal Knowledge Graph**를 지향한다.

모든 지식은 가능한 한 다음 구조로 연결한다.

```
Fact Pattern
    ↓
  Rule
    ↓
Authority
    ↓
Conclusion
```

**예시:**

```
명절상여금
    ↓
재직조건부 임금 판단규칙
    ↓
대법원 2013다2672
    ↓
통상임금 해당 여부
```

---

## 4. Knowledge Architecture

```
/my-labor-wiki

/raw
├── laws
├── cases
├── interpretations
├── company_norms
├── research_press
└── _triage

/wiki
├── concepts
├── rules
├── cases
├── laws
├── history
├── discussions
├── fact_patterns
├── logs
└── index.md

/templates
```

---

## 5. Authority Hierarchy

법적 권위(Legal Authority)와 실무 집행력(Enforcement Weight)을 구분한다.

### Legal Authority

| Level | 권위 유형 |
|-------|-----------|
| 1 | 헌법 / 법률 / 시행령 / 시행규칙 |
| 2 | 대법원 전원합의체 |
| 3 | 대법원 |
| 4 | 고등법원 / 지방법원 |
| 5 | 고용노동부 행정해석 / 예규 / 지침 |
| 6 | 단체협약 / 취업규칙 / 근로계약 |
| 7 | 학술논문 / 연구보고서 / 언론자료 |

---

### 5.1 Enforcement Weight

실무 집행 영향도를 별도 관리한다.

**허용값:** `critical` / `high` / `medium` / `low`

**예시:**

| 권위 유형 | authority_level | enforcement_weight |
|-----------|-----------------|-------------------|
| 고용노동부 행정해석 | 5 | high |
| 대법원 판례 | 3 | medium |
| 대법원 전원합의체 | 2 | high |
| 헌법 / 법률 | 1 | critical |

---

## 6. Conflict Resolution

상충 정보 발견 시 반드시 기록한다.

**원칙:** 상위 Authority 우선

**예외:** 판례와 행정해석이 상충하더라도, 실제 근로감독 행정집행이 행정해석 기준으로 수행된다면 반드시 기록한다.

**필수 기록 필드:**

- `conflict_status`
- `conflict_type`
- 행정해석 번호
- 실무 적용 현황

### 6.1 Conflict 해소 절차

충돌이 등록된 이후 해소 과정을 다음 절차로 관리한다.

**상태값:** `pending` / `resolved` / `unresolvable`

| 상태 | 의미 |
|------|------|
| `pending` | 충돌 등록 완료, 해소 검토 중 |
| `resolved` | 상위 Authority 확정 또는 실무 기준 확정으로 해소됨 |
| `unresolvable` | 법령 또는 판례 개정 없이 해소 불가 (지속 모니터링) |

**해소 시 필수 기록:**

- `conflict_resolution`: 해소 상태값
- `conflict_resolution_note`: 해소 근거 또는 실무 판단 요약
- `conflict_resolved_date`: 해소 확정일

충돌이 `unresolvable`로 분류된 경우, `review_trigger`에 관련 법령 개정 이벤트를 등록하여 재검토를 자동화한다.

---

## 7. Ingestion Workflow

```
RAW 추가
    ↓
Raw Auto Routing (raw 루트 파일을 하위 폴더로 이동)
    ↓
Metadata 등록 (ingestion_status: imported)
    ↓
Extract (ingestion_status: extracted)
    ↓
Link (ingestion_status: linked)
    ↓
Verify (ingestion_status: verified)
    ↓
Knowledge Graph 편입
```

### 7.1 ingestion_status 전이 조건

각 단계의 진입 조건을 반드시 충족해야 상태를 전진시킨다.

| 전이 | 조건 |
|------|------|
| `imported` → `extracted` | raw 문서에서 entity 식별 완료, entity_type 확정, id 부여 |
| `extracted` → `linked` | `related_*` 링크 1개 이상 연결 완료, Orphan 상태 해소 |
| `linked` → `verified` | `primary_authority` 검증 완료, conflict 검사 수행, `authority_level` 정합성 확인 |

조건을 충족하지 않은 상태 전진은 금지한다.

---

### 7.2 Raw Auto Routing 절차

새 source 처리 요청을 받으면 LLM은 먼저 `/raw/` 루트에 직접 놓인 파일을 검사한다. 루트 파일이 있으면 다음 순서로 처리한다.

1. 파일명과 접근 가능한 텍스트의 첫 부분을 기준으로 source 유형을 분류한다.
2. Section 2.1.1의 분류 기준에 따라 대상 raw 하위 폴더를 정한다.
3. 대상 폴더가 없으면 생성한다.
4. 같은 이름의 파일이 이미 있으면 덮어쓰지 않고 충돌 회피 파일명을 만든다.
5. 파일을 대상 폴더로 이동한다.
6. 이동 전 경로와 이동 후 경로를 `ROUTE_RAW` 로그로 기록한다.
7. 그 다음에만 entity 추출, 링크, 검증을 진행한다.

분류가 불확실한 파일은 `/raw/_triage/`로 이동하고, entity 생성은 하지 않는다.

---

## 8. Canonical Frontmatter Schema

### 8.1 공통 필드 (모든 entity_type 적용)

```yaml
---
id: ""                          # 고유 식별자 (예: rule-001, case-2013다2672)

entity_type: ""                 # concept / rule / case / law / history / discussion / fact_pattern

title: ""

status: draft                   # draft / verified / legacy

ingestion_status: imported      # imported / extracted / linked / verified

primary_authority: ""           # 주 근거 권위 (법령명 또는 판례번호)

authority_level: 7              # 1~7 (Section 5 참조)

enforcement_weight: low         # critical / high / medium / low

conflict_status: none           # none / active

conflict_type: none             # none / authority / temporal / interpretive / jurisdictional

conflict_resolution: ""         # pending / resolved / unresolvable (conflict_status: active일 때 필수)

conflict_resolution_note: ""    # 해소 근거 또는 실무 판단 요약

conflict_resolved_date: ""      # 해소 확정일

effective_from: 1900-01-01

effective_to: 9999-12-31

superseded_by: ""               # 이 엔티티를 대체한 상위 Rule 또는 Law ID

superseded_date: ""             # 대체 확정일 (판례 변경, 법령 개정 등)

review_cycle: annual            # monthly / quarterly / annual

review_trigger: []              # 재검토 트리거 이벤트 목록

related_concepts: []

related_rules: []

related_cases: []

related_laws: []

related_fact_patterns: []

related_raw: []                 # 필수: 원천 raw 문서 링크

source_locator: []              # 권장: 판시사항 번호, 조문 위치 등

source_excerpt: []              # 권장: 핵심 원문 발췌 (저작권 범위 내)

last_verified: ""

last_updated: ""
---
```

---

### 8.2 Case 전용 추가 필드

Case entity_type 문서는 공통 필드에 더하여 다음 필드를 반드시 포함한다.

```yaml
---
court_name: ""                  # 대법원 / 서울고등법원 / 서울중앙지방법원 등

case_number: ""                 # 예: 2013다2672

decision_date: ""               # 판결 선고일 (YYYY-MM-DD)

case_role: ""                   # leading / persuasive / conflicting / overruling

holding_summary: ""             # 판시 요지 (필수 — Lint Check 9 대상)

legal_principles: []            # 이 판결에서 추출된 법리 목록 (필수 — Lint Check 9 대상)
---
```

---

### 8.3 Rule 전용 추가 필드

Rule entity_type 문서는 공통 필드에 더하여 다음 필드를 포함한다.

```yaml
---
rule_type: ""                   # inclusion / exclusion / calculation / limitation / procedure

law_version: ""                 # 적용 법령 버전

law_revision_date: ""           # 해당 법령 개정일

wage_criteria: []               # 판단 기준 요소: ["정기성", "일률성", "고정성"] 등

wage_type: []                   # ["통상임금", "평균임금"] 등

worker_scope: ""                # 적용 대상 근로자 범위 (예: 전 직원 / 정규직 / 생산직)

calculation_unit: ""            # 산정 주기 및 단위 (예: 월 / 분기 / 연)

extinction_period: ""           # 소멸시효 (예: 3년)
---
```

---

### 8.4 Law 전용 추가 필드

Law entity_type 문서는 공통 필드에 더하여 다음 필드를 포함한다.

```yaml
---
law_version: ""                 # 현행 법령 버전

law_revision_date: ""           # 최근 개정일

promulgation_date: ""           # 공포일

enforcement_date: ""            # 시행일
---
```

---

## 9. Controlled Vocabulary

### entity_type
`concept` / `rule` / `case` / `law` / `history` / `discussion` / `fact_pattern`

### status
`draft` / `verified` / `legacy`

### ingestion_status
`imported` / `extracted` / `linked` / `verified`

### conflict_status
`none` / `active`

### conflict_type
`none` / `authority` / `temporal` / `interpretive` / `jurisdictional`

### conflict_resolution
`pending` / `resolved` / `unresolvable`

### review_cycle
`monthly` / `quarterly` / `annual`

### case_role
`leading` / `persuasive` / `conflicting` / `overruling`

### rule_type
`inclusion` / `exclusion` / `calculation` / `limitation` / `procedure`

### enforcement_weight
`critical` / `high` / `medium` / `low`

### wage_criteria (다중 선택 가능)
`정기성` / `일률성` / `고정성` / `근로대가성` / `사전확정성`

### wage_type (다중 선택 가능)
`통상임금` / `평균임금` / `최저임금` / `비과세`

---

## 10. Linking Protocol

### Mandatory Link Rules

| Entity | 최소 링크 요건 |
|--------|--------------|
| Concept | Rule 1개 이상 |
| Rule | Case 또는 Law 1개 이상, Authority 1개 이상 |
| Fact Pattern | Rule 1개 이상 |
| Case | Rule 1개 이상 |
| Law | History 권장 |

**Orphan Entity는 허용되지 않는다.**

신규 문서 생성 시 링크가 1개도 없는 상태로 저장하는 것을 금지한다. 링크 대상이 아직 존재하지 않는 경우, 연결 예정 엔티티를 stub으로 먼저 생성한 뒤 링크한다.

---

## 11. Source Provenance Protocol

모든 Rule, Case, Law 문서는 최소 1개 이상의 원천 출처를 가져야 한다.

**필수:** `related_raw`
**권장:** `source_locator`, `source_excerpt`

**예시:**

```yaml
related_raw:
  - "[[2013다2672_원문]]"

source_locator:
  - "판시사항 3"

source_excerpt:
  - "정기적이고 일률적으로 지급되는 금품..."
```

---

## 12. LLM Editing Rules

### 12.1 사전 탐색

문서 생성 전 반드시 수행한다.

1. 기존 그래프 탐색
2. 중복 Rule 탐색
3. 중복 Case 탐색
4. 중복 Fact Pattern 탐색

탐색 없이 신규 문서를 생성하는 것을 금지한다.

---

### 12.2 링크 강제

신규 생성 문서는 `related_*` 링크를 최소 1개 이상 포함해야 한다.

---

### 12.3 Rule First

개념 설명보다 판단 규칙을 우선 모델링한다.

**우선순위:** Rule → Case → Law → Concept

---

### 12.4 임금법 특화 추출 규칙

추출 시 다음 요소를 반드시 식별한다. 각 요소는 해당 entity_type의 전용 필드에 귀속시킨다.

| 추출 요소 | 귀속 필드 | 귀속 entity_type |
|-----------|-----------|-----------------|
| 적용 대상 근로자 범위 | `worker_scope` | Rule |
| 산정 주기 및 단위 | `calculation_unit` | Rule |
| 지급 조건 | `source_excerpt` + Rule 본문 | Rule |
| 통상임금성 / 평균임금성 | `wage_type` | Rule |
| 비과세 여부 | `wage_type` | Rule |
| 소멸시효 | `extinction_period` | Rule |
| 정기성 / 일률성 / 고정성 등 판단 요소 | `wage_criteria` | Rule |
| 전형 사실유형 (명절상여금 등) | Fact Pattern 본문 | fact_pattern |

---

### 12.5 Deduplication Rule

신규 엔티티 생성 전 반드시 다음을 검사한다.

1. 동일 사건번호
2. 동일 법조문
3. 동일 Rule
4. 동일 Fact Pattern

**중복 발견 시:** 신규 생성보다 링크 확장을 우선한다.

---

### 12.6 Supersession 처리 규칙

판례 변경(overruling) 또는 법령 개정으로 인해 기존 Rule 또는 Law가 무효화된 경우:

1. 기존 문서의 `status`를 `legacy`로 변경한다.
2. `superseded_by`에 대체 엔티티 ID를 기재한다.
3. `superseded_date`를 기재한다.
4. 대체 엔티티에서 `related_rules` 또는 `related_cases`로 역링크를 추가한다.
5. Log에 `DEPRECATE` 액션으로 기록한다.

기존 문서를 삭제하거나 덮어쓰는 것을 금지한다.

---

## 13. Log Protocol

로그는 **Append Only**이다. 수정 및 삭제를 금지한다.

**경로:** `/wiki/logs/YYYY-MM.md`

**형식:**

```
- [YYYY-MM-DD]
  Action: <허용 어휘>
  Target: <엔티티 ID 또는 파일 경로>
  Source: <근거 raw 문서 또는 외부 출처>
  Rationale: <변경 이유 또는 판단 근거>
```

### 13.1 허용 Action 어휘

| 어휘 | 의미 |
|------|------|
| `CREATE` | 신규 엔티티 생성 |
| `UPDATE` | 기존 엔티티 내용 수정 |
| `LINK` | 링크 추가 또는 수정 |
| `DEPRECATE` | 엔티티 legacy 처리 (superseded) |
| `CONFLICT_REGISTER` | 충돌 등록 |
| `CONFLICT_RESOLVE` | 충돌 해소 기록 |
| `LINT_RUN` | Lint 점검 실행 |
| `VERIFY` | 엔티티 verified 상태 확정 |
| `INGEST` | raw 문서 신규 추가 |
| `ROUTE_RAW` | raw 루트 파일을 적절한 raw 하위 폴더로 이동 |

---

## 14. Lint Protocol

사용자가 `Lint` 또는 `위키 점검`을 요청하면 다음 검사를 수행한다.

Lint 항목은 심각도(Severity)에 따라 처리 우선순위를 부여한다.

### Severity: Critical (즉시 처리)

**Check 1 — Rule Without Authority**
Rule 문서에 `primary_authority`가 없거나 `related_cases` 및 `related_laws`가 모두 비어 있는 경우.

**Check 2 — Broken Reference**
`related_*` 링크가 존재하지 않는 문서를 가리키는 경우.

---

### Severity: High (당일 처리)

**Check 3 — Orphan Entity**
`related_*` 링크가 하나도 없는 엔티티.

**Check 4 — Case Missing Holding**
Case 문서에 `holding_summary` 또는 `legal_principles`가 없는 경우.
→ 이 두 필드는 Frontmatter Schema(Section 8.2)에 명시된 필수 필드이다.

**Check 5 — Authority Mismatch**
`authority_level`과 `primary_authority` 값이 불일치하는 경우.
예: `authority_level: 1` + `primary_authority: 고용노동부 행정해석`

---

### Severity: Medium (주간 처리)

**Check 6 — Draft Backlog**
`status: draft`이고 `last_updated`가 30일 이상 경과한 문서.

**Check 7 — Stale Verification**
`review_cycle`에 따른 재검토 기한이 경과한 문서.
예: `review_cycle: annual`이고 `last_verified`가 365일 초과.

**Check 8 — Fact Pattern Without Rule**
Fact Pattern 문서에 `related_rules`가 없는 경우.

**Check 9 — Concept Without Rule**
Concept 문서에 `related_rules`가 없는 경우.

---

### Severity: Low (월간 처리)

**Check 10 — Conflict Review**
`conflict_status: active`이고 `conflict_resolution: pending` 상태가 90일 이상 경과한 문서.

**Check 11 — Raw Integrity**
`/raw/` 경로 문서의 내용이 최초 ingest 이후 변경된 흔적이 있는 경우.

**Check 12 — Ingestion Stall**
`ingestion_status`가 `imported` 또는 `extracted` 상태로 14일 이상 정체된 문서.

---

## 15. Repository Success Criteria

본 저장소는 다음 상태를 목표로 한다.

| # | 기준 |
|---|------|
| 1 | 모든 Concept가 Rule과 연결됨 |
| 2 | 모든 Rule이 Authority를 가짐 |
| 3 | 모든 Case가 Rule을 지원함 |
| 4 | 모든 Law가 최신 버전으로 검증됨 |
| 5 | 모든 Fact Pattern이 Rule과 연결됨 |
| 6 | Orphan Entity 0건 유지 |
| 7 | 출처 없는 Rule 0건 유지 |
| 8 | 모든 변경 이력 추적 가능 |
| 9 | GraphRAG 질의에서 추론 경로 제공 가능 |
| 10 | 노동법 실무 질의에 대해 근거 기반 답변 가능 |
| 11 | 모든 충돌(conflict)에 해소 상태 기록 |
| 12 | Superseded 엔티티의 대체 경로 추적 가능 |
| 13 | 모든 Case에 holding_summary 및 legal_principles 존재 |

---

*본 규약은 v1.1이며, 변경 시 Log에 `UPDATE` 액션으로 기록하고 버전을 갱신한다.*
