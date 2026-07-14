# 대한민국 임금법 Legal Knowledge Graph

대한민국 임금법의 법령·판례·행정해석을 Rule 중심으로 연결하는 Obsidian 호환 지식 그래프다. 원문은 `raw/`에 불변 보존하고, `wiki/`에는 출처 위치와 법적 시점을 추적할 수 있는 원자적 엔티티를 둔다.

## v1.3 핵심 모델

- `status`는 편집 상태(`draft`, `review`, `verified`)만 나타낸다.
- 법적 효력은 `legal_status`(`current`, `historical`, `superseded`, `overruled`, `future`, `unknown`)로 분리한다.
- 사람이 읽는 `primary_authority`와 함께 기계 해소 가능한 `primary_authority_id`, `authority_ids`를 사용한다.
- `evidence`는 `source_id`, 정확한 `locator`, 짧은 `excerpt`, 근거가 되는 claim ID인 `supports`를 한 레코드로 묶는다.
- `relations`는 `relation_type`과 `target_id`로 법적 의미가 있는 간선을 표현한다. 기존 `related_*` 링크는 Obsidian 탐색과 v1.2 호환을 위해 유지한다.
- 행정해석·지침은 `interpretation` 엔티티로 모델링한다.
- Rule은 `issue → elements → exceptions → conclusion`과 `temporal` 적용기간을 명시한다.
- canonical `id`는 변경하지 않는다. 교정 ID와 한글 사건번호는 `id_aliases` 및 `schemas/id-aliases.json`으로 해소한다.

정확한 필드와 허용값은 `schemas/frontmatter-v1.3.schema.json`, `schemas/vocabularies.json`, 예시는 `templates/`를 따른다.

## 폴더

| 경로 | 역할 |
|---|---|
| `raw/` | 수정하지 않는 원문 자료 |
| `wiki/` | Rule, Case, Law, Interpretation 등 그래프 엔티티 |
| `templates/` | v1.3 신규 문서 템플릿 |
| `schemas/` | JSON Schema, 통제 어휘, ID alias |
| `sources/` | source registry, 과거 경로 alias, raw manifest |
| `scripts/` | 외부 패키지가 필요 없는 검사·생성 도구 |
| `web/` | GitHub Pages용 CSS·JavaScript 원본 |
| `tests/qa_regression.jsonl` | 법률 QA 회귀 질문과 필수 권위·Rule ID |

## 요구 환경

Python 3.10 이상만 필요하다. PyYAML이나 jsonschema 등 외부 패키지를 설치하지 않는다. frontmatter는 저장소가 사용하는 YAML subset을 안전하게 읽으며 YAML tag, anchor, 임의 객체 생성은 거부한다.

## 웹사이트

웹사이트는 [GitHub Pages](https://yghnsim.github.io/Wage_Wiki/)에서 제공한다. `wiki/`의 전체 엔티티를 빌드 시 정적 HTML로 변환하므로 별도 서버나 데이터베이스가 필요하지 않다. 현재는 통상임금·평균임금, 성과급, 지급조건, 최저임금과 반환약정 쟁점을 중심으로 수록한다. 첫 화면은 전체 문서를 최신순으로 표시하며 제목·별칭·사건번호·본문 검색과 문서 유형 필터로 범위를 좁힐 수 있다. 편집 상태와 법적 상태는 각 문서 카드의 배지로 확인한다.

검증된 현행 Rule 중 사실유형과 주 권위가 모두 연결된 문서는 `사실관계 → 판단 규칙 → 근거 권위 → 결론`의 판단 경로로 표시한다. 상세 화면의 연결 문서는 대상별로 중복을 제거하고 복수 관계를 함께 표시하며, 근거는 source registry의 원문 제목과 locator를 사용한다.

문서 본문의 `mermaid` 코드 블록은 빌드 시 외부 패키지나 브라우저 스크립트 없이 반응형 SVG 흐름도로 변환한다. 지원 문법은 `flowchart LR/RL/TD/TB/BT`, 사각형·둥근 사각형·판단 노드와 선택지 라벨이 붙은 방향 간선이다. 방향 선언은 모두 인식하되 좁은 상세 본문에서도 글자가 읽히도록 공개 화면에서는 위에서 아래로 재배치한다. 지원하지 않는 Mermaid 문법은 코드로 노출하지 않고 빌드를 실패시켜 배포 전에 발견한다.

로컬 빌드와 검사는 다음과 같다.

```text
python scripts/build_site.py --output build/site --site-url "http://localhost:8000/"
python scripts/check_site.py build/site --output build/site-check.json
python -m http.server 8000 --directory build/site
```

브라우저에서 `http://localhost:8000/`을 연다. 생성물은 `build/site/`에만 만들어지고 커밋하지 않는다. `raw/`의 PDF·HTML은 Pages 산출물에서 제외하며 상세 페이지에는 검토된 외부 원문 URL만 표시한다.

`.github/workflows/pages.yml`은 `main` push와 수동 실행 시 lint, 단위 테스트, QA·manifest 검사를 통과한 뒤 사이트를 생성하고 내부 링크를 점검하여 Pages에 배포한다. 프로젝트 사이트의 `/Wage_Wiki/` 경로와 향후 사용자 도메인 변경은 `actions/configure-pages`가 제공하는 URL을 빌드에 전달해 처리한다.

## 점검과 생성

아래 명령은 Windows, macOS, Linux에서 동일하다. `--output`을 생략하면 표준 출력으로 내보낸다.

```text
python scripts/lint_wiki.py --output build/lint-report.json --strict-v13 --fail-on high
python scripts/check_qa_regression.py
python scripts/build_manifest.py --output sources/raw-manifest.jsonl
python scripts/build_manifest.py --check sources/raw-manifest.jsonl
python scripts/build_dashboard.py --output build/dashboard.md
python scripts/export_graph.py --output build/graph.json
python scripts/build_search_index.py --chunks build/chunks.jsonl --database build/wage_wiki.sqlite
python scripts/search_wiki.py "통상임금 고정성" --database build/wage_wiki.sqlite --include-review --include-historical
python scripts/build_site.py --output build/site --site-url "https://example.invalid/Wage_Wiki/"
python scripts/check_site.py build/site --output build/site-check.json
python -m unittest discover -s scripts/tests -v
```

Lint JSON에는 심각도별 집계와 모든 문제의 `code`, `path`, `field`, `message`가 담긴다. 최종 CI 기준은 `--strict-v13 --fail-on high`다. 이관 작업 중 임시 진단에만 `--fail-on critical`을 사용할 수 있으며 완료 판정에는 사용할 수 없다. QA 회귀셋은 `check_qa_regression.py`와 lint 양쪽에서 JSONL 구문, 중복 test ID, 날짜, `required_authority_ids`, `required_rule_ids`의 실제 존재와 Rule 유형을 검사한다.

정적 대시보드와 graph export는 생성물이다. 위키 내용처럼 수동 편집하지 않는다. graph JSON은 v1.3 typed relation, 권위, evidence edge를 우선하고 v1.2 `related_*` 간선에는 `related_to`를 사용한다.

검색 인덱스는 섹션 단위 JSONL chunk와 SQLite FTS5 데이터베이스를 만든다. `.sqlite`와 chunk는 재생성 산출물이므로 커밋하지 않는다. 검색 기본값은 실행일 기준 `verified + current`다. `--include-review`는 편집 상태를 `review + verified`로 넓히되 `draft`는 계속 제외한다. `--include-historical`은 법적 상태 필터만 완화하고 `--as-of` 유효기간 필터는 유지하므로, 기준일보다 뒤에 시행되는 future 문서가 무차별 포함되지 않는다. 과거 시점 질의는 `--as-of YYYY-MM-DD`를 명시한다.

## v1.2 → v1.3 이관

이관기는 기본적으로 dry-run이며 `--write` 없이는 어떤 wiki 파일도 바꾸지 않는다.

```text
python scripts/migrate_schema_v13.py --as-of-date 2026-07-10 --output build/migration-plan.json
python scripts/migrate_schema_v13.py --as-of-date 2026-07-10 --write
```

이관기는 다음을 수행한다.

1. 편집 `status`와 `legal_status`를 분리한다.
2. 외부 URL을 `related_raw`에서 `source_urls`로 옮긴다.
3. 사건번호·관련 권위 링크로 해소 가능한 `primary_authority_id`, `authority_ids`를 채운다.
4. canonical ID는 유지하고 정의된 `id_aliases`를 추가한다.
5. v1.2 링크를 보수적인 typed relation으로 옮긴다.
6. 통제 어휘 밖의 `wage_criteria`는 `decision_factors`로 이동한다.
7. 근거를 추측하지 않고 `evidence` 수동 검토 대상을 JSON에 보고한다.

v1.2에는 검증자 식별자가 없으므로 기본 이관은 기존 `verified`를 `review`로 내려 재검증을 요구한다. 이번 작업에서 실제 법률 내용까지 재검증한 경우에만 `--verified-by <검증자-ID>`를 사용한다. 이 옵션은 해당 문서의 ingestion, `last_verified`, `last_checked`를 이관 기준일로 갱신하므로 단순 형식 변환에는 사용하지 않는다.

기본 review 주기는 Rule·Law·Interpretation과 일반 Discussion이 `quarterly`, 제목에 `최신 동향`이 있는 Discussion이 `monthly`다. Case는 기준일로부터 최근 2년 이내 선고분을 `quarterly`, 그 이전 판례를 `annual`로 두고, Concept·History·Fact Pattern은 `annual`로 둔다. 기존 명시값을 자동으로 덮어쓰지 않는다. 계획을 검토한 후 아래 옵션을 명시해야 기존 값을 정책값으로 바꾼다.

```text
python scripts/migrate_schema_v13.py --write --apply-review-policy
```

공식 판결 원문이 공개되지 않았음을 검색으로 확인한 사건은 반복 가능한 옵션으로 표시한다. 해당 사건에 공식 검색 URL이 있어야 lint 예외가 성립한다.

```text
python scripts/migrate_schema_v13.py --write \
  --unavailable-case-id case-92다11466 \
  --unavailable-case-id case-2019다244942
```

PowerShell에서는 줄 연속 문자를 쓰지 않고 한 줄로 실행하거나 백틱을 사용한다. 이관 후에는 반드시 lint JSON의 미해소 권위, evidence, source availability를 검토한다.

## 출처와 원문 무결성

source ID는 `raw-<source_type>-<stable-number-or-slug>` 형식을 권장한다. 예: `raw-case-2020da219454`. ID는 파일 경로가 바뀌어도 유지하며 `sources/registry.yaml`의 `path`만 갱신한다. 등록되지 않은 원문에는 manifest가 내용 기반 `raw-sha256-<16자리>` ID를 부여한다.

`sources/raw-manifest.jsonl`은 경로, 분류, 미디어 타입, 바이트 크기, SHA-256을 저장한다. 재생성 후 diff가 생기면 원문 신규 편입인지 무결성 훼손인지 확인하고, 관련 로그를 append-only로 남긴다. 과거 로그의 옛 파일 경로는 로그를 고치지 않고 `sources/path_aliases.yaml`에 추가한다.

manifest는 `.gitkeep`, OS 메타파일, 미완료 다운로드와 임시 확장자를 제외한다. 점(`.`)으로 시작하는 실제 raw가 의도적으로 존재하면 `--include-hidden`을 명시해 포함한다. 이 옵션을 사용해도 `.gitkeep`, `.DS_Store`, `Thumbs.db`, `*.tmp`, `*.part`, `*.crdownload`은 원문이 아니므로 제외된다.

## 최신성 운영

| 대상 | 탐지 | 검증 주기 |
|---|---|---|
| 법령·시행령 | 매일 | 분기 및 개정 즉시 |
| 대법원·고용노동부 | 매주 | 분기 및 신규 권위 즉시 |
| 최신 동향 Discussion | 매월 | 월간 |
| 일반 Discussion | 분기 | 분기 |
| 최근 2년 Case | trigger 기반 | 분기 |
| 그 이전 Case·Concept·History·Fact Pattern | trigger 기반 | 연간 |

변경이 탐지되면 `authority_ids`, `relations`, `review_trigger`로 영향을 받는 Rule만 우선 재검증한다. `last_checked`는 존재·최신성 점검일, `last_verified`는 법률 내용 검증일이므로 서로 대체하지 않는다.

GitHub Actions는 push/PR 외에 매주 월요일 UTC 00:00(한국시간 09:00)에 실행되며 수동 실행도 지원한다. 예약 실행은 별도 고정일을 주지 않아 실행 당일을 기준으로 `review_cycle` 초과를 계산하고 strict v1.3 High 기준을 적용한다.

## 완료 기준

- 통제 어휘 위반, 중복 ID, 깨진 링크·관계, 상태 모순 0건
- 공식 원문이 없는 Case 0건. 다만 `unavailable_official`과 공식 검색 증거가 있는 경우 예외
- verified 문서의 `last_checked`와 `last_verified`가 `last_updated` 이상
- verified Rule·Case·Law·Interpretation의 핵심 주장마다 source locator 존재
- review_cycle 초과 0건과 raw manifest SHA-256 정합성 유지
- QA 회귀셋의 필수 Authority·Rule ID 해소율 100%

저장소 운영 원칙, 권위 계층, 로그 형식, raw 보존 규칙은 `AGENT.md`를 따른다.
