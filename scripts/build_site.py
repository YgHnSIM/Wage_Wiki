#!/usr/bin/env python3
"""Build a dependency-free static website for GitHub Pages."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from graph_contract import RELATED_FIELDS
from kg_common import (
    Entity,
    as_list,
    entity_lookup,
    load_entities,
    load_json,
    resolve_entity_ref,
    scalar_text,
    wiki_targets,
)
from site_markdown import (
    _plain_text,
    _summary,
    _truncate_summary,
    render_inline,
    render_markdown,
)
from source_catalog import registry_title_map


SITE_TITLE = "대한민국 임금법 판례 지식베이스"
SITE_DESCRIPTION = "통상임금·평균임금과 성과급, 지급조건, 최저임금 쟁점을 판례와 판단 규칙으로 연결한 지식베이스"
DEFAULT_REPOSITORY_URL = "https://github.com/YgHnSIM/Wage_Wiki"
ASSET_VERSION = "dev"

TOPIC_LINKS = (
    (
        "통상임금",
        "통상임금",
        "고정성 폐기 이후의 판단 기준, 상여금과 지급조건을 살펴봅니다.",
    ),
    (
        "평균임금·성과급",
        "성과급 평균임금",
        "공공기관·사기업 성과급과 퇴직금 산입 기준을 살펴봅니다.",
    ),
    (
        "재직·근무조건",
        "재직조건",
        "재직조건과 근무일수 조건의 효력 및 통상임금성을 살펴봅니다.",
    ),
    (
        "최저임금·택시",
        "택시 최저임금",
        "소정근로시간과 초과운송수입금의 판단 구조를 살펴봅니다.",
    ),
    (
        "반환약정",
        "반환약정",
        "사이닝보너스·지원비 반환과 위약예정 금지 기준을 살펴봅니다.",
    ),
)

TYPE_ORDER = {
    "rule": 0,
    "case": 1,
    "law": 2,
    "interpretation": 3,
    "fact_pattern": 4,
    "concept": 5,
    "discussion": 6,
    "history": 7,
}
TYPE_LABELS = {
    "rule": "판단 규칙",
    "case": "판례",
    "law": "법령",
    "interpretation": "행정해석",
    "fact_pattern": "사실유형",
    "concept": "개념",
    "discussion": "쟁점",
    "history": "연혁",
}
TYPE_PREFIXES = {
    "rule": "RU",
    "case": "CA",
    "law": "LA",
    "interpretation": "IN",
    "fact_pattern": "FA",
    "concept": "CO",
    "discussion": "DI",
    "history": "HI",
}
STATUS_LABELS = {"verified": "검증됨", "review": "검토 중", "draft": "초안"}
LEGAL_STATUS_LABELS = {
    "current": "현행",
    "future": "장래 적용",
    "historical": "역사적 자료",
    "superseded": "대체됨",
    "overruled": "판례 변경됨",
    "unknown": "상태 미확인",
}
ENFORCEMENT_LABELS = {
    "critical": "매우 높음",
    "high": "높음",
    "medium": "중간",
    "low": "낮음",
}
SOURCE_AVAILABILITY_LABELS = {
    "available": "원문 공개",
    "partial": "일부 공개",
    "unavailable_official": "공식 전문 미공개",
}
RELATION_LABELS = {
    "establishes": "확립함",
    "applies": "적용함",
    "interprets": "해석함",
    "distinguishes": "구별함",
    "overrules": "판례 변경함",
    "supersedes": "대체함",
    "conflicts_with": "충돌함",
    "exception_to": "예외임",
    "illustrated_by": "사실유형으로 설명됨",
    "supports": "뒷받침함",
    "cites": "인용함",
    "amends": "개정함",
    "implements": "시행함",
    "related_to": "관련됨",
    "has_primary_authority": "주 권위",
    "has_authority": "근거 권위",
}


def _flatten(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, dict):
        result: list[str] = []
        for item in value.values():
            result.extend(_flatten(item))
        return result
    if isinstance(value, list):
        result = []
        for item in value:
            result.extend(_flatten(item))
        return result
    return [str(value)]


def entity_slug(entity_id: str) -> str:
    ascii_part = re.sub(r"[^a-z0-9]+", "-", entity_id.casefold()).strip("-")
    digest = hashlib.sha256(entity_id.encode("utf-8")).hexdigest()[:8]
    prefix = ascii_part[:48].rstrip("-") or "entity"
    return f"{prefix}-{digest}"


def _date_info(entity: Entity) -> tuple[str, str]:
    data = entity.data
    entity_type = scalar_text(data.get("entity_type"))
    candidates: list[tuple[str, str]] = []
    if entity_type == "case":
        candidates.append(("선고", scalar_text(data.get("decision_date"))))
    elif entity_type == "law":
        candidates.extend(
            [("시행", scalar_text(data.get("enforcement_date"))), ("공포", scalar_text(data.get("promulgation_date")))]
        )
    elif entity_type == "interpretation":
        candidates.append(("발행", scalar_text(data.get("issue_date"))))
    candidates.extend(
        [("적용", scalar_text(data.get("effective_from"))), ("기준", scalar_text(data.get("as_of_date")))]
    )
    for label, value in candidates:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return label, value
    return "날짜", ""


def _format_date(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value or "미기재"
    year, month, day = value.split("-")
    return f"{year}. {month}. {day}."


def _sort_date(entity: Entity) -> str:
    return _date_info(entity)[1] or scalar_text(entity.data.get("as_of_date")) or "0000-00-00"


def _effective_on(data: dict[str, Any], as_of: str) -> bool:
    start = scalar_text(data.get("effective_from")) or "1900-01-01"
    end = scalar_text(data.get("effective_to")) or "9999-12-31"
    return start <= as_of <= end


def _entity_records(entities: list[Entity], slugs: dict[str, str]) -> list[dict[str, Any]]:
    ordered = sorted(
        entities,
        key=lambda entity: (
            TYPE_ORDER.get(scalar_text(entity.data.get("entity_type")), 99),
            scalar_text(entity.data.get("title")).casefold(),
        ),
    )
    counters: Counter[str] = Counter()
    records: list[dict[str, Any]] = []
    for entity in ordered:
        data = entity.data
        entity_type = scalar_text(data.get("entity_type"))
        entity_id = scalar_text(data.get("id"))
        counters[entity_type] += 1
        number = f"{TYPE_PREFIXES.get(entity_type, 'EN')}-{counters[entity_type]:02d}"
        summary = _summary(entity)
        date_label, date_value = _date_info(entity)
        aliases = [scalar_text(value) for value in as_list(data.get("aliases")) if scalar_text(value)]
        search_parts = [
            scalar_text(data.get("title")),
            *aliases,
            *[scalar_text(value) for value in as_list(data.get("id_aliases"))],
            scalar_text(data.get("case_number")),
            scalar_text(data.get("primary_authority")),
            scalar_text(data.get("holding_summary")),
            scalar_text(data.get("conclusion")),
            scalar_text(data.get("definition")),
            scalar_text(data.get("issue")),
            *[scalar_text(value) for value in as_list(data.get("wage_type"))],
            *[scalar_text(value) for value in as_list(data.get("wage_criteria"))],
            *[scalar_text(value) for value in as_list(data.get("decision_factors"))],
            _plain_text(entity.body),
        ]
        search_text = " ".join(dict.fromkeys(part for part in search_parts if part))
        records.append(
            {
                "id": entity_id,
                "number": number,
                "title": scalar_text(data.get("title")) or entity.path.stem,
                "type": entity_type,
                "typeLabel": TYPE_LABELS.get(entity_type, entity_type),
                "status": scalar_text(data.get("status")),
                "statusLabel": STATUS_LABELS.get(scalar_text(data.get("status")), scalar_text(data.get("status"))),
                "legalStatus": scalar_text(data.get("legal_status")) or "unknown",
                "legalStatusLabel": LEGAL_STATUS_LABELS.get(
                    scalar_text(data.get("legal_status")) or "unknown", scalar_text(data.get("legal_status"))
                ),
                "effectiveFrom": scalar_text(data.get("effective_from")) or "1900-01-01",
                "effectiveTo": scalar_text(data.get("effective_to")) or "9999-12-31",
                "asOfDate": scalar_text(data.get("as_of_date")),
                "dateLabel": date_label,
                "date": date_value,
                "dateDisplay": _format_date(date_value),
                "sortDate": date_value or "0000-00-00",
                "authorityLevel": data.get("authority_level"),
                "enforcementWeight": scalar_text(data.get("enforcement_weight")),
                "sourceAvailability": scalar_text(data.get("source_availability")),
                "summary": summary,
                "aliases": aliases,
                "caseNumber": scalar_text(data.get("case_number")),
                "searchText": search_text,
                "url": f"entities/{slugs[entity_id]}/",
            }
        )
    return records


def _first_related_entity(
    entity: Entity,
    target_type: str,
    by_id: dict[str, Entity],
    names: dict[str, list[Entity]],
) -> Entity | None:
    field_by_type = {
        "rule": "related_rules",
        "case": "related_cases",
        "law": "related_laws",
        "interpretation": "related_interpretations",
        "fact_pattern": "related_fact_patterns",
        "concept": "related_concepts",
    }
    field = field_by_type.get(target_type)
    if field:
        for target_name in wiki_targets(entity.data.get(field)):
            matches = resolve_entity_ref(target_name, names)
            if len(matches) == 1 and scalar_text(matches[0].data.get("entity_type")) == target_type:
                return matches[0]
    for relation in as_list(entity.data.get("relations")):
        if not isinstance(relation, dict):
            continue
        target = by_id.get(scalar_text(relation.get("target_id")))
        if target and scalar_text(target.data.get("entity_type")) == target_type:
            return target
    return None


def _decision_path(
    entity: Entity,
    by_id: dict[str, Entity],
    names: dict[str, list[Entity]],
) -> list[dict[str, str]]:
    entity_type = scalar_text(entity.data.get("entity_type"))
    rule = entity if entity_type == "rule" else _first_related_entity(entity, "rule", by_id, names)
    if not rule:
        return []
    fact = entity if entity_type == "fact_pattern" else _first_related_entity(rule, "fact_pattern", by_id, names)
    if not fact:
        fact = _first_related_entity(entity, "fact_pattern", by_id, names)
    authority = by_id.get(scalar_text(rule.data.get("primary_authority_id")))
    if not authority and entity_type in {"case", "law", "interpretation"}:
        authority = entity
    conclusion = _plain_text(scalar_text(rule.data.get("conclusion")))
    if not fact or not authority or not conclusion:
        return []
    return [
        {
            "label": "사실관계",
            "text": scalar_text(fact.data.get("title")),
            "target_id": scalar_text(fact.data.get("id")),
        },
        {
            "label": "판단 규칙",
            "text": scalar_text(rule.data.get("title")),
            "target_id": scalar_text(rule.data.get("id")),
        },
        {
            "label": "근거 권위",
            "text": scalar_text(authority.data.get("title")),
            "target_id": scalar_text(authority.data.get("id")),
        },
        {
            "label": "결론",
            "text": _truncate_summary(conclusion, limit=180),
            "target_id": "",
        },
    ]


def _judgment_paths(
    entities: list[Entity],
    by_id: dict[str, Entity],
    names: dict[str, list[Entity]],
    records_by_id: dict[str, dict[str, Any]],
    as_of: str,
    limit: int = 4,
) -> list[dict[str, Any]]:
    rules = [
        entity
        for entity in entities
        if scalar_text(entity.data.get("entity_type")) == "rule"
        and scalar_text(entity.data.get("status")) == "verified"
        and scalar_text(entity.data.get("legal_status")) == "current"
        and _effective_on(entity.data, as_of)
    ]
    rules.sort(key=lambda entity: records_by_id[scalar_text(entity.data.get("id"))]["sortDate"], reverse=True)
    paths: list[dict[str, Any]] = []
    for rule in rules:
        steps = _decision_path(rule, by_id, names)
        if len(steps) != 4:
            continue
        record = records_by_id[scalar_text(rule.data.get("id"))]
        paths.append({"record": record, "steps": steps})
        if len(paths) >= limit:
            break
    return paths


def _load_source_titles(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    return registry_title_map(path.parent.parent)


def _canonical(site_url: str, relative: str = "") -> str:
    if not site_url:
        return ""
    return site_url.rstrip("/") + "/" + relative.lstrip("/")


def _document(
    *,
    title: str,
    description: str,
    body: str,
    asset_prefix: str,
    canonical_url: str,
    page_class: str,
    include_app: bool = False,
) -> str:
    canonical_tag = f'<link rel="canonical" href="{html.escape(canonical_url, quote=True)}">' if canonical_url else ""
    social_url = f'<meta property="og:url" content="{html.escape(canonical_url, quote=True)}">' if canonical_url else ""
    favicon_url = html.escape(f"{asset_prefix}favicon.svg?v={ASSET_VERSION}", quote=True)
    stylesheet_url = html.escape(f"{asset_prefix}styles.css?v={ASSET_VERSION}", quote=True)
    script_url = html.escape(f"{asset_prefix}app.js?v={ASSET_VERSION}", quote=True)
    script = f'<script defer src="{script_url}"></script>' if include_app else ""
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>{html.escape(title)}</title>
  <meta name="description" content="{html.escape(description, quote=True)}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="{SITE_TITLE}">
  <meta property="og:title" content="{html.escape(title, quote=True)}">
  <meta property="og:description" content="{html.escape(description, quote=True)}">
  {social_url}
  {canonical_tag}
  <link rel="icon" href="{favicon_url}" type="image/svg+xml">
  <link rel="stylesheet" href="{stylesheet_url}">
  {script}
</head>
<body class="{html.escape(page_class, quote=True)}">
  <a class="skip-link" href="#main">본문으로 건너뛰기</a>
  {body}
</body>
</html>
"""


def _site_header(home_prefix: str, repository_url: str) -> str:
    safe_home = html.escape(home_prefix, quote=True)
    return f"""<header class="site-header">
  <a class="wordmark" href="{safe_home}"><span>WAGE</span><span>WIKI</span></a>
  <nav aria-label="주요 메뉴">
    <a href="{safe_home}#explore">문서 탐색</a>
    <a href="{safe_home}about/">데이터 안내</a>
    <a href="{html.escape(repository_url, quote=True)}">GitHub 저장소</a>
  </nav>
</header>"""


def _badge(value: str, label: str, kind: str) -> str:
    return f'<span class="badge badge--{html.escape(kind)}" data-value="{html.escape(value, quote=True)}">{html.escape(label)}</span>'


def _record_card(record: dict[str, Any]) -> str:
    return f"""<article class="result-card">
  <div class="result-card__number" aria-hidden="true">{html.escape(record['number'])}</div>
  <div class="result-card__body">
    <div class="result-card__meta">
      <span>{html.escape(record['typeLabel'])}</span>
      <span>{html.escape(record['dateLabel'])} {html.escape(record['dateDisplay'])}</span>
    </div>
    <h3><a href="{html.escape(record['url'], quote=True)}">{html.escape(record['title'])}</a></h3>
    <p>{html.escape(record['summary'])}</p>
    <div class="badges">
      {_badge(record['status'], record['statusLabel'], 'editorial')}
      {_badge(record['legalStatus'], record['legalStatusLabel'], 'legal')}
    </div>
  </div>
</article>"""


def _decision_path_steps_html(
    steps: list[dict[str, str]],
    slugs: dict[str, str],
    *,
    link_prefix: str,
    current_id: str = "",
) -> str:
    items: list[str] = []
    for index, step in enumerate(steps, 1):
        target_id = step.get("target_id", "")
        text = html.escape(step.get("text", ""))
        if target_id and target_id in slugs and target_id != current_id:
            content = f'<a href="{html.escape(link_prefix + slugs[target_id] + "/", quote=True)}">{text}</a>'
        else:
            content = f"<span>{text}</span>"
        items.append(
            f'<li><span class="decision-path__number">{index:02d}</span>'
            f'<small>{html.escape(step.get("label", ""))}</small>{content}</li>'
        )
    return f'<ol class="decision-path__steps">{"".join(items)}</ol>'


def _home_judgment_paths(paths: list[dict[str, Any]], slugs: dict[str, str]) -> str:
    if not paths:
        return ""
    items: list[str] = []
    for path in paths:
        record = path["record"]
        steps = _decision_path_steps_html(path["steps"], slugs, link_prefix="entities/")
        items.append(
            f"""<article class="judgment-path">
  <header><span>{html.escape(record['number'])}</span><time datetime="{html.escape(record['date'], quote=True)}">{html.escape(record['dateDisplay'])}</time></header>
  <h3><a href="{html.escape(record['url'], quote=True)}">{html.escape(record['title'])}</a></h3>
  {steps}
</article>"""
        )
    return f"""<section class="judgment-paths" aria-labelledby="paths-title">
  <div class="section-heading section-heading--split">
    <div><p class="section-label">검증된 현행 판단 규칙</p><h2 id="paths-title">최근 판단 경로</h2></div>
    <p class="section-note">사실관계에서 결론까지 연결된 최신 규칙입니다.</p>
  </div>
  <div class="judgment-paths__list">{''.join(items)}</div>
</section>"""


def _home_page(
    records: list[dict[str, Any]],
    counts: Counter[str],
    status_counts: Counter[str],
    legal_counts: Counter[str],
    as_of: str,
    site_url: str,
    repository_url: str,
    judgment_paths: list[dict[str, Any]],
    slugs: dict[str, str],
) -> str:
    trusted = [
        item
        for item in records
        if item["status"] == "verified" and item["legalStatus"] == "current" and item["effectiveFrom"] <= as_of <= item["effectiveTo"]
    ]
    ordered_records = sorted(records, key=lambda item: item["sortDate"], reverse=True)
    initial = ordered_records[:18]
    type_buttons = [f'<button type="button" class="type-filter is-active" data-type="all" data-label="전체 문서" aria-pressed="true">전체 <span>{len(records)}</span></button>']
    for entity_type in sorted(counts, key=lambda value: TYPE_ORDER.get(value, 99)):
        type_label = TYPE_LABELS.get(entity_type, entity_type)
        type_buttons.append(
            f'<button type="button" class="type-filter" data-type="{html.escape(entity_type, quote=True)}" '
            f'data-label="{html.escape(type_label, quote=True)}" aria-pressed="false">'
            f'{html.escape(type_label)} <span>{counts[entity_type]}</span></button>'
        )
    initial_cards = "".join(_record_card(item) for item in initial)
    paths_html = _home_judgment_paths(judgment_paths, slugs)
    topic_links = "".join(
        f'<a href="?q={html.escape(quote(query), quote=True)}#explore"><strong>{html.escape(title)}</strong>'
        f'<span>{html.escape(description)}</span></a>'
        for title, query, description in TOPIC_LINKS
    )
    formatted_as_of = html.escape(_format_date(as_of))
    body = f"""{_site_header('./', repository_url)}
<main id="main" tabindex="-1">
  <section class="hero" aria-labelledby="hero-title">
    <div class="hero__copy">
      <p class="section-label">통상임금·평균임금 중심 임금법 판례 지식베이스</p>
      <h1 id="hero-title">판례와 규칙을<br>한 흐름으로 읽습니다.</h1>
      <p class="hero__description">통상임금·평균임금, 성과급, 지급조건, 최저임금 쟁점을 사실관계·판단 규칙·근거 권위·결론의 흐름으로 탐색합니다.</p>
      <a class="text-link" href="#explore">문서 탐색 시작</a>
    </div>
    <div class="hero__folio" aria-label="데이터 현황">
      <div><strong>{len(records):02d}</strong><span>전체 문서</span></div>
      <div><strong>{len(trusted):02d}</strong><span>검증된 현행 지식</span></div>
      <div><strong>{legal_counts.get('future', 0):02d}</strong><span>장래 적용</span></div>
      <p>기준일 {formatted_as_of}</p>
    </div>
  </section>

  <section class="current-strip" aria-label="현재 데이터 기준">
    <div><span>편집 상태</span><strong>검증 {status_counts.get('verified', 0)} · 검토 {status_counts.get('review', 0)} · 초안 {status_counts.get('draft', 0)}</strong></div>
    <div><span>법적 상태</span><strong>현행 {legal_counts.get('current', 0)} · 장래 {legal_counts.get('future', 0)}</strong></div>
    <div><span>스키마</span><strong>v1.3</strong></div>
  </section>

  {paths_html}

  <section class="topic-index" aria-labelledby="topics-title">
    <div><p class="section-label">현재 수록 범위</p><h2 id="topics-title">주제별 시작점</h2></div>
    <nav aria-label="주제별 문서 탐색">{topic_links}</nav>
  </section>

  <section class="explorer" id="explore" aria-labelledby="explore-title" data-index-url="assets/entities.json?v={ASSET_VERSION}">
    <div class="section-heading section-heading--split">
      <div><p class="section-label">전체 지식베이스</p><h2 id="explore-title">문서 탐색</h2></div>
      <p class="result-status" id="result-status" aria-live="polite">전체 문서 {len(records)}개 · {len(initial)}개 표시</p>
    </div>
    <form class="search-panel" id="search-form" role="search" action="./" method="get">
      <label for="search-input">문서 검색</label>
      <div class="search-panel__control">
        <input id="search-input" name="q" type="search" autocomplete="off" placeholder="제목, 사건번호, 쟁점을 검색하세요" aria-describedby="search-help">
        <button type="button" id="clear-search" hidden>지우기</button>
      </div>
      <p id="search-help">제목·별칭·사건번호·본문을 검색합니다. 슬래시(/) 또는 Ctrl+K로 검색창에 이동할 수 있습니다.</p>
    </form>
    <fieldset class="type-filters"><legend>문서 유형</legend><div>{''.join(type_buttons)}</div></fieldset>

    <noscript><p class="notice">유형 필터를 사용하려면 JavaScript가 필요합니다. 아래에는 최신 문서 일부가 표시됩니다.</p></noscript>
    <div class="results" id="results">{initial_cards}</div>
    <div class="load-more-wrap"><button type="button" id="load-more" hidden>더 보기</button></div>
    <div class="empty-state" id="empty-state" hidden><h3 id="empty-title">검색 결과가 없습니다.</h3><p id="empty-description">검색어를 바꾸거나 다른 문서 유형을 선택해 보세요.</p></div>
  </section>

  <section class="disclaimer" aria-labelledby="disclaimer-title">
    <h2 id="disclaimer-title">이용 안내</h2>
    <p>이 사이트는 연구와 정보 제공을 위한 지식베이스이며 개별 사건에 대한 법률 자문이 아닙니다. 문서의 기준일, 편집 상태, 법적 상태와 연결된 원문을 함께 확인하세요.</p>
    <a class="text-link" href="about/">데이터 구성과 검증 기준 보기</a>
  </section>
</main>
<footer class="site-footer"><p>Wage Wiki · 기준일 {formatted_as_of}</p><p><a href="{html.escape(repository_url, quote=True)}">GitHub에서 원본 보기</a></p></footer>"""
    return _document(
        title=SITE_TITLE,
        description=SITE_DESCRIPTION,
        body=body,
        asset_prefix="assets/",
        canonical_url=_canonical(site_url),
        page_class="home-page",
        include_app=True,
    )


def _related_entities(
    entity: Entity,
    by_id: dict[str, Entity],
    names: dict[str, list[Entity]],
) -> list[tuple[Entity, list[str], list[str]]]:
    data = entity.data
    source_id = scalar_text(data.get("id"))
    found: dict[str, dict[str, Any]] = {}

    def add(target: Entity, relation: str, note: str = "", *, generic: bool = False) -> None:
        target_id = scalar_text(target.data.get("id"))
        if not target_id or target_id == source_id:
            return
        item = found.setdefault(target_id, {"target": target, "relations": [], "notes": []})
        relations = item["relations"]
        if generic and relations:
            return
        if not generic and "related_to" in relations:
            relations.remove("related_to")
        if relation not in relations:
            relations.append(relation)
        if note and note not in item["notes"]:
            item["notes"].append(note)

    for relation in as_list(data.get("relations")):
        if isinstance(relation, dict):
            target = by_id.get(scalar_text(relation.get("target_id")))
            if target:
                add(target, scalar_text(relation.get("relation_type")) or "related_to", scalar_text(relation.get("note")))
    primary = by_id.get(scalar_text(data.get("primary_authority_id")))
    if primary:
        add(primary, "has_primary_authority")
    for authority_id in as_list(data.get("authority_ids")):
        target = by_id.get(scalar_text(authority_id))
        if target and target is not primary:
            add(target, "has_authority")
    for field in RELATED_FIELDS:
        for target_name in wiki_targets(data.get(field)):
            matches = resolve_entity_ref(target_name, names)
            if len(matches) == 1:
                add(matches[0], "related_to", generic=True)
    ordered = sorted(
        found.values(),
        key=lambda item: (
            TYPE_ORDER.get(scalar_text(item["target"].data.get("entity_type")), 99),
            scalar_text(item["target"].data.get("title")).casefold(),
        ),
    )
    return [(item["target"], item["relations"], item["notes"]) for item in ordered]


def _status_notices(data: dict[str, Any]) -> list[str]:
    notices: list[str] = []
    status = scalar_text(data.get("status"))
    legal_status = scalar_text(data.get("legal_status"))
    if status == "review":
        notices.append("이 문서는 검토 중입니다. 검증된 자료 및 연결된 원문과 함께 확인하세요.")
    elif status == "draft":
        notices.append("이 문서는 초안입니다. 실무 판단의 단독 근거로 사용하지 마세요.")
    if legal_status == "future":
        date = scalar_text(data.get("effective_from")) or scalar_text(data.get("enforcement_date"))
        notices.append(f"이 문서는 {_format_date(date)}부터 적용될 예정입니다. 현재 시점의 법리와 구분하세요.")
    elif legal_status == "superseded":
        notices.append("이 문서는 후속 규칙 또는 법령으로 대체되었습니다. 현행 판단에 직접 적용하지 마세요.")
    elif legal_status == "overruled":
        notices.append("이 문서의 법리는 후속 판례로 변경되었습니다. 현행 판례를 먼저 확인하세요.")
    elif legal_status == "historical":
        notices.append("이 문서는 법리의 변화를 설명하는 역사적 자료입니다.")
    if scalar_text(data.get("source_availability")) in {"partial", "unavailable_official"}:
        note = scalar_text(data.get("source_availability_note"))
        notices.append("공식 원문이 전부 공개되지 않았습니다." + (f" {note}" if note else ""))
    return notices


def _metadata_rows(data: dict[str, Any]) -> list[tuple[str, str]]:
    fields = [
        ("주 권위", "primary_authority"),
        ("권위 단계", "authority_level"),
        ("실무 영향도", "enforcement_weight"),
        ("적용 시작", "effective_from"),
        ("적용 종료", "effective_to"),
        ("기준일", "as_of_date"),
        ("검증일", "last_verified"),
        ("원문 공개", "source_availability"),
    ]
    result: list[tuple[str, str]] = []
    for label, key in fields:
        value = data.get(key)
        if value in (None, "", [], {}):
            continue
        if key in {"effective_from", "effective_to", "as_of_date", "last_verified"}:
            rendered = "종료일 없음" if key == "effective_to" and scalar_text(value) == "9999-12-31" else _format_date(scalar_text(value))
        elif key == "authority_level":
            rendered = f"{value}단계"
        elif key == "enforcement_weight":
            rendered = ENFORCEMENT_LABELS.get(scalar_text(value), scalar_text(value))
        elif key == "source_availability":
            rendered = SOURCE_AVAILABILITY_LABELS.get(scalar_text(value), scalar_text(value))
        else:
            rendered = " · ".join(_flatten(value))
        result.append((label, rendered))
    return result


def _domain_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def _parse_source_url(url: str) -> tuple[Any, str]:
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").casefold()
        parsed.port
    except ValueError as exc:
        raise RuntimeError(f"invalid source URL: {url}") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or any(ord(character) < 32 for character in url)
    ):
        raise RuntimeError(f"invalid source URL: {url}")
    return parsed, host


def _source_label(url: str) -> str:
    parsed, host = _parse_source_url(url)
    path = parsed.path.casefold()
    if _domain_matches(host, "scourt.go.kr"):
        if path.endswith(".pdf") or "/sjudge/" in path:
            return "대법원 판결문 PDF"
        if "/news/" in path:
            return "대법원 공개자료"
        return "법원 공개 원문"
    if _domain_matches(host, "law.go.kr"):
        return "국가법령정보센터 원문"
    if _domain_matches(host, "moel.go.kr"):
        return "고용노동부 공개자료"
    return "외부 원문"


def _toc_entries(body_html: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for match in re.finditer(r'<h[2-4]\s+id="([^"]+)">(.*?)</h[2-4]>', body_html, flags=re.S):
        label = html.unescape(re.sub(r"<[^>]+>", "", match.group(2))).strip()
        if label:
            result.append((match.group(1), label))
    return result


def _support_labels(value: Any) -> list[str]:
    patterns = (
        (("conclusion", "holding"), "결론"),
        (("element", "factor", "criteria"), "판단 요소"),
        (("definition", "identity"), "정의"),
        (("scope", "applicable", "temporal"), "적용 범위"),
        (("payment", "obligation"), "지급 의무"),
        (("supersed", "overrul", "repeal"), "대체·변경 관계"),
        (("fact",), "사실관계"),
        (("rule", "principle"), "판단 규칙"),
    )
    result: list[str] = []
    for raw in as_list(value):
        claim = scalar_text(raw).casefold()
        label = next((label for needles, label in patterns if any(needle in claim for needle in needles)), "핵심 주장")
        if label not in result:
            result.append(label)
    return result


def _related_groups_html(
    related: list[tuple[Entity, list[str], list[str]]],
    slugs: dict[str, str],
) -> str:
    groups: dict[str, list[str]] = {}
    for target, relations, notes in related:
        entity_type = scalar_text(target.data.get("entity_type"))
        target_id = scalar_text(target.data.get("id"))
        relation_tags = "".join(
            f"<span>{html.escape(RELATION_LABELS.get(relation, relation))}</span>" for relation in relations
        )
        note_html = f'<p>{html.escape(" / ".join(notes))}</p>' if notes else ""
        item = (
            f'<li><a href="../{slugs[target_id]}/"><strong>{html.escape(scalar_text(target.data.get("title")))}</strong></a>'
            f'<div class="relation-tags">{relation_tags}</div>{note_html}</li>'
        )
        groups.setdefault(entity_type, []).append(item)
    sections: list[str] = []
    for entity_type in sorted(groups, key=lambda value: TYPE_ORDER.get(value, 99)):
        sections.append(
            f'<section class="relations__group"><h3>{html.escape(TYPE_LABELS.get(entity_type, entity_type))}</h3>'
            f'<ul>{"".join(groups[entity_type])}</ul></section>'
        )
    return "".join(sections)


def _entity_page(
    entity: Entity,
    record: dict[str, Any],
    by_id: dict[str, Entity],
    names: dict[str, list[Entity]],
    slugs: dict[str, str],
    site_url: str,
    repository_url: str,
    branch: str,
    source_titles: dict[str, str],
) -> str:
    data = entity.data
    entity_id = scalar_text(data.get("id"))
    title = scalar_text(data.get("title"))
    current_slug = slugs[entity_id]
    body_html = render_markdown(
        entity.body,
        names,
        slugs,
        link_for=lambda slug: f"../{slug}/",
        current_id=entity_id,
        title=title,
    )
    related = _related_entities(entity, by_id, names)
    related_html = _related_groups_html(related, slugs)
    metadata_rows = _metadata_rows(data)
    primary_authority_id = scalar_text(data.get("primary_authority_id"))

    def metadata_row(label: str, value: str) -> str:
        if label == "주 권위" and primary_authority_id in slugs:
            content = f'<a href="../{slugs[primary_authority_id]}/">{html.escape(value)}</a>'
        else:
            content = html.escape(value)
        row_class = {
            "주 권위": "document-meta__row--authority",
            "적용 시작": "document-meta__row--period-start",
            "적용 종료": "document-meta__row--period-end",
        }.get(label, "document-meta__row--detail")
        return f'<div class="{row_class}"><dt>{html.escape(label)}</dt><dd>{content}</dd></div>'

    primary_labels = {"주 권위", "적용 시작", "적용 종료"}
    primary_metadata_html = "".join(metadata_row(label, value) for label, value in metadata_rows if label in primary_labels)
    secondary_metadata_html = "".join(metadata_row(label, value) for label, value in metadata_rows if label not in primary_labels)
    toc = _toc_entries(body_html)
    toc_html = "".join(
        f'<li><a href="#{html.escape(anchor, quote=True)}">{html.escape(label)}</a></li>' for anchor, label in toc
    )
    path_steps = _decision_path(entity, by_id, names)
    decision_path_html = ""
    if path_steps:
        decision_path_html = f"""<section class="document-decision-path" aria-labelledby="decision-path-title">
  <div class="document-decision-path__heading"><p class="section-label">이 문서의 법적 연결</p><h2 id="decision-path-title">판단 경로</h2></div>
  {_decision_path_steps_html(path_steps, slugs, link_prefix="../", current_id=entity_id)}
</section>"""
    notices = _status_notices(data)
    notice_html = "".join(f'<p class="status-notice">{html.escape(notice)}</p>' for notice in notices)

    evidence_items: list[str] = []
    for evidence in as_list(data.get("evidence")):
        if not isinstance(evidence, dict):
            continue
        locator = scalar_text(evidence.get("locator"))
        excerpt = scalar_text(evidence.get("excerpt"))
        verified = scalar_text(evidence.get("verified_on"))
        source_id = scalar_text(evidence.get("source_id"))
        source_title = source_titles.get(source_id, "등록 원문")
        supports = _support_labels(evidence.get("supports"))
        supports_html = f'<span>뒷받침: {html.escape(" · ".join(supports))}</span>' if supports else ""
        evidence_items.append(
            f"""<li>
  <div class="evidence__meta"><strong>{html.escape(source_title)}</strong><span>{html.escape(locator)}</span>{supports_html}</div>
  <blockquote>{html.escape(excerpt)}</blockquote>
  {f'<p>검증일 {html.escape(_format_date(verified))}</p>' if verified else ''}
</li>"""
        )
    evidence_html = ""
    if evidence_items:
        evidence_html = f"""<section class="document-section evidence" aria-labelledby="evidence-title">
  <div class="document-section__heading"><span>{len(evidence_items):02d}</span><h2 id="evidence-title">근거</h2></div>
  <ol>{''.join(evidence_items)}</ol>
</section>"""

    source_links: list[str] = []
    for source_index, source_url in enumerate(as_list(data.get("source_urls")), 1):
        url = scalar_text(source_url)
        if not url:
            continue
        _, host = _parse_source_url(url)
        source_label = _source_label(url)
        accessible_label = f"{title} - {source_label} {source_index}"
        source_links.append(
            f'<li><a href="{html.escape(url, quote=True)}" rel="noreferrer" aria-label="{html.escape(accessible_label, quote=True)}">'
            f'<span>{html.escape(host)}</span><strong>{html.escape(source_label)} {source_index}</strong></a></li>'
        )
    sources_html = ""
    if source_links:
        sources_html = f"""<section class="document-section sources" aria-labelledby="sources-title">
  <div class="document-section__heading"><span>{len(source_links):02d}</span><h2 id="sources-title">외부 원문</h2></div>
  <ul>{''.join(source_links)}</ul>
</section>"""

    tech_fields = ["schema_version", "id", "ingestion_status", "review_cycle", "last_checked", "last_updated", "verified_by"]
    tech_rows = "".join(
        f"<div><dt>{html.escape(key)}</dt><dd>{html.escape(' · '.join(_flatten(data.get(key))))}</dd></div>"
        for key in tech_fields
        if data.get(key) not in (None, "", [], {})
    )
    repo_source = f"{repository_url.rstrip('/')}/blob/{quote(branch)}/{quote(entity.relative_path, safe='/')}"
    date_parts = record["date"].split("-") if record["date"] else []
    if len(date_parts) == 3:
        rail_date = f"<strong>{date_parts[0]}</strong><span>{date_parts[1]}.{date_parts[2]}</span>"
    else:
        rail_date = "<strong>날짜</strong><span>미기재</span>"
    body = f"""{_site_header('../../', repository_url)}
<main id="main" tabindex="-1">
  <nav class="breadcrumb" aria-label="현재 위치"><a href="../../">홈</a><span>/</span><a href="../../#explore">{html.escape(record['typeLabel'])}</a><span>/</span><span aria-current="page">{html.escape(record['number'])}</span></nav>
  <article class="document">
    <header class="document-hero">
      <div class="date-rail"><p>{html.escape(record['dateLabel'])}</p>{rail_date}<small>{html.escape(record['number'])}</small></div>
      <div class="document-title">
        <p class="section-label">{html.escape(record['typeLabel'])}</p>
        <h1>{html.escape(title)}</h1>
        <div class="badges">{_badge(record['status'], record['statusLabel'], 'editorial')}{_badge(record['legalStatus'], record['legalStatusLabel'], 'legal')}</div>
        <p class="document-summary">{html.escape(record['summary'])}</p>
        {notice_html}
      </div>
      <aside class="document-meta" aria-label="문서 메타데이터">
        <dl class="document-meta__primary">{primary_metadata_html}</dl>
        <details class="document-meta__more" open><summary>검증 정보</summary><dl>{secondary_metadata_html}</dl></details>
      </aside>
    </header>

    {decision_path_html}

    <div class="document-grid">
      <nav class="document-index" aria-label="이 문서의 목차">
        <strong>{html.escape(record['number'])}</strong>
        <span>문서 목차</span>
        <ol>{toc_html}</ol>
      </nav>
      <div class="prose">{body_html}</div>
      <aside class="relations" aria-labelledby="relations-title">
        <div class="aside-heading"><span>{len(related):02d}</span><h2 id="relations-title">연결 문서</h2></div>
        {related_html}
      </aside>
    </div>

    <div class="document-lower">
      {evidence_html}
      {sources_html}
      <details class="technical-meta"><summary>기술 메타데이터</summary><dl>{tech_rows}</dl><a href="{html.escape(repo_source, quote=True)}">GitHub에서 이 문서 편집본 보기</a></details>
    </div>
  </article>
</main>
<footer class="site-footer"><p>Wage Wiki · {html.escape(record['id'])}</p><p><a href="../../#explore">전체 문서로 돌아가기</a></p></footer>"""
    return _document(
        title=f"{title} | Wage Wiki",
        description=record["summary"][:160] or SITE_DESCRIPTION,
        body=body,
        asset_prefix="../../assets/",
        canonical_url=_canonical(site_url, f"entities/{current_slug}/"),
        page_class=f"entity-page entity-page--{record['type']}",
        include_app=True,
    )


def _about_page(
    records: list[dict[str, Any]],
    counts: Counter[str],
    status_counts: Counter[str],
    legal_counts: Counter[str],
    as_of: str,
    site_url: str,
    repository_url: str,
) -> str:
    type_rows = "".join(
        f"<tr><th scope=\"row\">{html.escape(TYPE_LABELS.get(key, key))}</th><td>{counts[key]}</td></tr>"
        for key in sorted(counts, key=lambda value: TYPE_ORDER.get(value, 99))
    )
    status_rows = "".join(
        f"<tr><th scope=\"row\">{html.escape(STATUS_LABELS.get(key, key))}</th><td>{status_counts[key]}</td></tr>"
        for key in ("verified", "review", "draft")
        if status_counts[key]
    )
    legal_rows = "".join(
        f"<tr><th scope=\"row\">{html.escape(LEGAL_STATUS_LABELS.get(key, key))}</th><td>{legal_counts[key]}</td></tr>"
        for key in ("current", "future", "superseded", "overruled", "historical", "unknown")
        if legal_counts[key]
    )
    body = f"""{_site_header('../', repository_url)}
<main id="main" class="about" tabindex="-1">
  <header class="about-hero"><p class="section-label">데이터 안내</p><h1>무엇을, 어떤 기준으로<br>보여주는가</h1><p>Wage Wiki는 현재 통상임금·평균임금, 성과급, 지급조건, 최저임금과 반환약정 쟁점을 중심으로 구축 중입니다. Markdown 원본의 구조화된 메타데이터와 본문을 정적 HTML로 변환하며, 원문 PDF·HTML을 복제하지 않고 공식 외부 주소만 연결합니다.</p></header>
  <section class="about-grid" aria-labelledby="coverage-title">
    <div class="section-heading"><p class="section-label">기준일 {html.escape(_format_date(as_of))}</p><h2 id="coverage-title">수록 범위</h2></div>
    <div class="table-wrap"><table><thead><tr><th>문서 유형</th><th>건수</th></tr></thead><tbody>{type_rows}</tbody></table></div>
    <div class="table-wrap"><table><thead><tr><th>편집 상태</th><th>건수</th></tr></thead><tbody>{status_rows}</tbody></table></div>
    <div class="table-wrap"><table><thead><tr><th>법적 상태</th><th>건수</th></tr></thead><tbody>{legal_rows}</tbody></table></div>
  </section>
  <section class="about-copy">
    <h2>두 가지 상태를 분리합니다.</h2>
    <p><strong>편집 상태</strong>는 문서가 초안, 검토 중, 검증됨 중 어디에 있는지를 뜻합니다. <strong>법적 상태</strong>는 법리가 현행인지, 장래 적용인지, 대체되거나 판례 변경된 것인지를 뜻합니다. 검증된 문서라도 역사적 법리일 수 있으므로 두 상태를 함께 확인해야 합니다.</p>
    <h2>검색과 문서 유형으로 전체 자료를 탐색합니다.</h2>
    <p>첫 화면은 전체 문서를 최신순으로 표시합니다. 제목·별칭·사건번호·본문을 검색하거나 판단 규칙, 판례, 법령, 행정해석, 사실유형 등 문서 유형으로 범위를 좁힐 수 있습니다. 각 카드의 편집 상태와 법적 상태 배지로 검증 여부와 적용 시점을 구분합니다.</p>
    <h2>판단 경로와 근거를 함께 제공합니다.</h2>
    <p>사실관계에서 판단 규칙, 근거 권위, 결론으로 이어지는 경로와 함께 원문 제목, 위치, 짧은 발췌, 검증일과 공식 외부 주소를 표시합니다. 같은 연결 문서는 한 번만 보여주고 확립·적용·해석·대체 관계를 함께 표기합니다.</p>
    <h2>정적 사이트로 운영합니다.</h2>
    <p>사이트는 GitHub Actions에서 다시 생성되어 GitHub Pages로 배포됩니다. 서버, 사용자 계정, 광고·분석 스크립트를 사용하지 않으며 검색과 유형 필터링은 브라우저 안에서만 처리됩니다.</p>
  </section>
  <section class="disclaimer"><h2>책임 범위</h2><p>이 사이트는 연구와 정보 제공을 위한 자료입니다. 실제 사건에는 사실관계, 적용 시점, 단체협약·취업규칙 등 추가 요소가 영향을 줄 수 있으므로 필요한 경우 전문가의 검토를 받으세요.</p><a class="text-link" href="../#explore">문서 탐색으로 돌아가기</a></section>
</main>
<footer class="site-footer"><p>Wage Wiki · 전체 {len(records)}개 문서</p><p><a href="{html.escape(repository_url, quote=True)}">GitHub 저장소</a></p></footer>"""
    return _document(
        title=f"데이터 안내 | {SITE_TITLE}",
        description="Wage Wiki의 수록 범위, 편집·법적 상태, 탐색 기준과 근거 표시 방법",
        body=body,
        asset_prefix="../assets/",
        canonical_url=_canonical(site_url, "about/"),
        page_class="about-page",
    )


def _redirect_page(target: str, canonical_url: str) -> str:
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>문서 이동 | Wage Wiki</title><meta http-equiv="refresh" content="0; url={html.escape(target, quote=True)}">
<link rel="canonical" href="{html.escape(canonical_url, quote=True)}"></head>
<body><p>문서 주소가 변경되었습니다. <a href="{html.escape(target, quote=True)}">새 주소로 이동</a></p></body></html>
"""


def _not_found(site_url: str, repository_url: str) -> str:
    home_url = _canonical(site_url) if site_url else "./"
    asset_prefix = _canonical(site_url, "assets/") if site_url else "assets/"
    body = f"""{_site_header(home_url, repository_url)}<main id="main" class="not-found" tabindex="-1"><p class="error-code">404</p><h1>페이지를 찾을 수 없습니다.</h1><p>주소가 변경되었거나 존재하지 않는 문서입니다.</p><a class="text-link" href="{html.escape(home_url, quote=True)}#explore">전체 문서 보기</a></main>"""
    return _document(
        title=f"페이지를 찾을 수 없음 | {SITE_TITLE}",
        description="요청한 Wage Wiki 페이지를 찾을 수 없습니다.",
        body=body,
        asset_prefix=asset_prefix,
        canonical_url=_canonical(site_url, "404.html"),
        page_class="error-page",
    )


def _safe_output(root: Path, output: Path) -> Path:
    root = root.resolve()
    output = output.resolve()
    build_root = (root / "build").resolve()
    if output == build_root or build_root not in output.parents:
        raise ValueError("site output must be a child directory of the repository build directory")
    return output


def _validated_site_url(site_url: str) -> str:
    if not site_url:
        return ""
    try:
        parsed = urlparse(site_url)
        host = parsed.hostname
        parsed.port
    except ValueError as exc:
        raise ValueError(f"invalid site URL: {site_url}") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or any(ord(character) < 32 for character in site_url)
    ):
        raise ValueError("site URL must be an absolute HTTP(S) URL without a query or fragment")
    return site_url.rstrip("/") + "/"


def build_site(
    root: Path,
    output: Path,
    *,
    site_url: str = "",
    repository_url: str = DEFAULT_REPOSITORY_URL,
    branch: str = "main",
    asset_source: Path | None = None,
) -> dict[str, Any]:
    global ASSET_VERSION
    root = root.resolve()
    output = _safe_output(root, output)
    site_url = _validated_site_url(site_url)
    asset_source = (asset_source or root / "web" / "assets").resolve()
    entities, parse_issues = load_entities(root)
    if parse_issues:
        messages = "; ".join(item["message"] for item in parse_issues[:5])
        raise RuntimeError(f"frontmatter parse failed: {messages}")
    if not entities:
        raise RuntimeError("no wiki entities found")
    for required in ("styles.css", "app.js", "favicon.svg"):
        if not (asset_source / required).is_file():
            raise RuntimeError(f"missing web asset: {asset_source / required}")
    asset_digest = hashlib.sha256()
    for asset_name in ("styles.css", "app.js", "favicon.svg"):
        asset_digest.update((asset_source / asset_name).read_bytes())

    by_id, names = entity_lookup(entities)
    slugs = {entity_id: entity_slug(entity_id) for entity_id in by_id}
    if len(set(slugs.values())) != len(slugs):
        raise RuntimeError("entity slug collision detected")
    records = _entity_records(entities, slugs)
    records_json = json.dumps(records, ensure_ascii=False, separators=(",", ":")) + "\n"
    asset_digest.update(records_json.encode("utf-8"))
    ASSET_VERSION = asset_digest.hexdigest()[:12]
    records_by_id = {record["id"]: record for record in records}
    counts = Counter(record["type"] for record in records)
    status_counts = Counter(record["status"] for record in records)
    legal_counts = Counter(record["legalStatus"] for record in records)
    as_of = max((record["asOfDate"] for record in records if record["asOfDate"]), default=dt.date.today().isoformat())
    judgment_paths = _judgment_paths(entities, by_id, names, records_by_id, as_of)
    source_titles = _load_source_titles(root / "sources" / "registry.yaml")

    if output.exists():
        shutil.rmtree(output)
    (output / "assets").mkdir(parents=True)
    shutil.copy2(asset_source / "styles.css", output / "assets" / "styles.css")
    shutil.copy2(asset_source / "app.js", output / "assets" / "app.js")
    shutil.copy2(asset_source / "favicon.svg", output / "assets" / "favicon.svg")
    (output / "index.html").write_text(
        _home_page(
            records,
            counts,
            status_counts,
            legal_counts,
            as_of,
            site_url,
            repository_url,
            judgment_paths,
            slugs,
        ),
        encoding="utf-8",
        newline="\n",
    )
    (output / "404.html").write_text(_not_found(site_url, repository_url), encoding="utf-8", newline="\n")
    (output / "about").mkdir()
    (output / "about" / "index.html").write_text(
        _about_page(records, counts, status_counts, legal_counts, as_of, site_url, repository_url),
        encoding="utf-8",
        newline="\n",
    )
    (output / "assets" / "entities.json").write_text(
        records_json, encoding="utf-8", newline="\n"
    )

    for entity in entities:
        entity_id = scalar_text(entity.data.get("id"))
        target = output / "entities" / slugs[entity_id]
        target.mkdir(parents=True)
        target.joinpath("index.html").write_text(
            _entity_page(
                entity,
                records_by_id[entity_id],
                by_id,
                names,
                slugs,
                site_url,
                repository_url,
                branch,
                source_titles,
            ),
            encoding="utf-8",
            newline="\n",
        )

    aliases = load_json(root / "schemas" / "id-aliases.json", {}).get("aliases_to_canonical", {})
    aliases = aliases if isinstance(aliases, dict) else {}
    for entity in entities:
        entity_id = scalar_text(entity.data.get("id"))
        for alias in as_list(entity.data.get("id_aliases")):
            aliases.setdefault(scalar_text(alias), entity_id)
    redirect_count = 0
    for alias, canonical_id in aliases.items():
        canonical_id = scalar_text(canonical_id)
        if not alias or canonical_id not in slugs:
            continue
        alias_dir = output / "aliases" / entity_slug(scalar_text(alias))
        alias_dir.mkdir(parents=True, exist_ok=True)
        target = f"../../entities/{slugs[canonical_id]}/"
        alias_dir.joinpath("index.html").write_text(
            _redirect_page(target, _canonical(site_url, f"entities/{slugs[canonical_id]}/")),
            encoding="utf-8",
            newline="\n",
        )
        redirect_count += 1

    sitemap_urls = [_canonical(site_url), _canonical(site_url, "about/")]
    sitemap_urls.extend(_canonical(site_url, record["url"]) for record in records)
    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    sitemap += "".join(f"  <url><loc>{html.escape(url)}</loc></url>\n" for url in sitemap_urls if url)
    sitemap += "</urlset>\n"
    (output / "sitemap.xml").write_text(sitemap, encoding="utf-8", newline="\n")
    robots_sitemap = f"Sitemap: {_canonical(site_url, 'sitemap.xml')}\n" if site_url else ""
    (output / "robots.txt").write_text(f"User-agent: *\nAllow: /\n{robots_sitemap}", encoding="utf-8", newline="\n")
    build_info = {
        "schema_version": "1.3",
        "as_of_date": as_of,
        "entities": len(records),
        "redirects": redirect_count,
        "entity_types": dict(sorted(counts.items())),
        "editorial_status": dict(sorted(status_counts.items())),
        "legal_status": dict(sorted(legal_counts.items())),
    }
    (output / "build-info.json").write_text(
        json.dumps(build_info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return build_info


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path("build/site"))
    parser.add_argument("--site-url", default="")
    parser.add_argument("--repository-url", default=DEFAULT_REPOSITORY_URL)
    parser.add_argument("--branch", default="main")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    try:
        report = build_site(
            root,
            output,
            site_url=args.site_url,
            repository_url=args.repository_url,
            branch=args.branch,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"site build failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
