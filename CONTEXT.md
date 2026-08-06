# Wage_Wiki Domain Context

Wage_Wiki는 한국 노동법 및 임금 체계에 관한 규칙 기반 법률 지식 그래프(Legal Knowledge Graph) 프로젝트입니다.

## Language

**법률 지식 엔티티 (Wiki Entity)**:
`raw/` 소스로부터 정규화되어 `wiki/`에 작성된 표준화된 지식 단위(Law, Rule, Case, Interpretation, Guide, Concept 등).
_Avoid_: 노트, 문서, 파일, 문서조각

**원시 사료 (Raw Source)**:
변형 없이 보존되는 판례, 해석례, 법령, 개정안 등의 원문 사료 (`raw/`).
_Avoid_: 기초자료, 원본문서, 텍스트파일

**청구항/규범 단위 (Claim Anchor)**:
`claim:` 네임스페이스를 가지는 개별 법률적 판단 기준 또는 계산 규칙 단위.
_Avoid_: 조항, 포인트, 룰셋

**증거/출처 (Evidence Locator)**:
`evidence:` 네임스페이스를 가지며 원시 사료 내의 위치 및 근거 조항을 지칭하는 앵커.
_Avoid_: 레퍼런스, 링크, 참조

**통상임금 (Ordinary Wage)**:
근로자에게 정기적·일률적·고정적으로 소정근로 또는 총근로에 대해 지급하기로 정해진 시간급/일급/주급/월급 금액.
_Avoid_: 기본급, 통상수당

**평균임금 (Average Wage)**:
산정해야 할 사유가 발생한 날 이전 3개월 동안에 그 근로자에게 지급된 임금의 총액을 그 기간의 총일수로 나눈 금액.
_Avoid_: 평균수당, 실질임금

**고정성 (Fixedness)**:
업적, 성과, 기타 추가적인 조건과 관계없이 임금이 당연히 지급될 것이 확정되어 있는 성질.
_Avoid_: 확실성, 보장성

**포괄임금약정 (Comprehensive Wage Agreement)**:
근로시간의 산정이 어렵거나 업무 성격상 시간외근로가 당연히 예상되는 경우 수당을 분할하지 않고 일정액을 법정수당으로 합산하여 지급하는 약정.
_Avoid_: 포괄수당계약, 퉁치기계약

**4원 결합 검증 (4-way Triad)**:
지식 엔티티 추가 시 `wiki/` 엔티티, `claim:`/`evidence:` 앵커, `fact_pattern`, `qa_regression` 테스트를 1:1:1:1로 결합하는 검증 방식.
_Avoid_: 단편 엔티티 작성, 초안 누락

**지식화율 (Knowledge Normalization Coverage)**:
`raw/` 폴더에 존재하는 원시 사료가 `wiki/` 내 정규화 엔티티로 변환·매핑된 비율.
_Avoid_: 파싱율, 정제율

