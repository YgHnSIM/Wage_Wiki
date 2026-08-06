# 0002. 4원 결합 검증(4-way Triad) 정규화 표준 및 작성 순서

Wage_Wiki 원시 사료 정규화 작업 시 지식 단위의 품질 무결성과 실무 검증성을 담보하기 위한 산출물 구성 기준을 정의합니다.

## 맥락 및 결정 (Context & Decision)

단순 판례/해석례 텍스트 요약에 그치지 않고 법적 근거 추적성 및 자동화 검증 가능성을 보장하기 위해 다음과 같은 4원 결합 검증 표준을 적용합니다:

1. **사료 우선순위 (Priority Order)**: 1차 정규화는 법적 수권력이 높은 `raw/cases/`(판례) 및 `raw/interpretations/`(행정해석) 항목을 대상으로 수행합니다.
2. **4원 결합 구조 (4-way Triad)**: 하나의 지식 정규화 작업 단위는 아래 4개 요소를 반드시 단일 커밋으로 결합하여 생성합니다:
   - `wiki/cases/` 또는 `wiki/interpretations/` 엔티티 Markdown 문서
   - `claim:` (판단 규칙) 및 `evidence:` (원시 사료 앵커) 위치 매핑
   - `wiki/fact_patterns/` 구체적 사건 시나리오 문서
   - `tests/qa_regression.jsonl` 검증 레코드
3. **사이트 파이프라인 통합**: Mermaid 관계도 시각화, FTS 검색 인덱스, 대시보드 지식화율 통계를 `scripts/build_site.py` 및 `scripts/build_dashboard.py`와 연동하여 자동 업데이트합니다.
