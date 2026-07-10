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
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import quote, urlparse

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


SITE_TITLE = "대한민국 임금법 지식베이스"
SITE_DESCRIPTION = "판례·법령·행정해석과 판단 규칙을 근거와 시점에 따라 연결한 임금법 지식베이스"
DEFAULT_REPOSITORY_URL = "https://github.com/YgHnSIM/Wage_Wiki"
ASSET_VERSION = "dev"

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
HEADING_LABELS = {
    "2026 Case Update": "2026년 판례 업데이트",
    "Administrative Position": "행정해석상 입장",
    "Application": "적용",
    "Application Order": "적용 순서",
    "Article 44-4": "제44조의4",
    "Authority": "근거 권위",
    "Authority Note": "권위 메모",
    "Boundary Rule": "한계 기준",
    "Case Flow": "판례 흐름",
    "Change": "변경 내용",
    "Conclusion": "결론",
    "Condition Agreement": "조건 합의",
    "Current Direction": "현재 방향",
    "Current Legal Position": "현행 법적 입장",
    "Decision Path": "판단 경로",
    "Definition": "정의",
    "Distinction from Fixedness": "고정성과의 구별",
    "Earlier Critiques": "종전 비판",
    "Effect": "효력",
    "Effect of Recent Performance-Pay Cases": "최근 성과급 판례의 영향",
    "Facts": "사실관계",
    "Former Administrative Rule": "종전 행정 기준",
    "Graph Role": "그래프 내 역할",
    "Historical Boundary": "역사적 적용 한계",
    "Historical Use Only": "역사적 참고에 한정",
    "Holding": "판시 요약",
    "Issue": "쟁점",
    "Legal Principles": "법적 원칙",
    "Lineage": "법리 계보",
    "Notes": "검토 메모",
    "Operative Changes": "주요 개정 내용",
    "Operative Terms": "적용 조항",
    "Origin": "기원",
    "Performance Pay Minimum Guarantee": "성과급 최소보장",
    "Positions": "견해",
    "Practical Application": "실무 적용",
    "Practical Assessment": "실무 판단",
    "Practical Notes": "실무 메모",
    "Provision": "조문",
    "Reasoning": "판단 이유",
    "Revision Notes": "개정 메모",
    "Rule": "판단 규칙",
    "Rule Application": "규칙 적용",
    "Rule Connection": "규칙 연결",
    "Rule Links": "관련 규칙",
    "Scope": "적용 범위",
    "Significance": "의미",
    "Staged Commencement": "단계별 시행",
    "Supersession": "대체 관계",
    "Temporal Scope": "시간적 적용 범위",
    "Timeline": "연혁",
    "Version Note": "버전 메모",
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
RELATED_FIELDS = (
    "related_concepts",
    "related_rules",
    "related_cases",
    "related_laws",
    "related_interpretations",
    "related_fact_patterns",
)
SEARCH_FIELDS = (
    "aliases",
    "id_aliases",
    "case_number",
    "case_numbers",
    "document_number",
    "holding_summary",
    "legal_principles",
    "issue",
    "elements",
    "exceptions",
    "conclusion",
    "wage_type",
    "wage_criteria",
    "decision_factors",
    "primary_authority",
    "source_excerpt",
    "evidence",
)

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
LIST_RE = re.compile(r"^\s*[-*+]\s+(.+)$")
ORDERED_LIST_RE = re.compile(r"^\s*\d+[.)]\s+(.+)$")
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")
INLINE_TOKEN_RE = re.compile(
    r"`([^`\n]+)`"
    r"|\[\[([^\]|#]+)(?:#([^\]|]+))?(?:\|([^\]]+))?\]\]"
    r"|\[([^\]]+)\]\((https?://[^\s)]+)\)"
)


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


def _slug_fragment(value: str) -> str:
    value = re.sub(r"[`*_~]", "", value.strip().lower())
    value = re.sub(r"[^0-9a-z가-힣]+", "-", value, flags=re.I)
    return value.strip("-") or "section"


def entity_slug(entity_id: str) -> str:
    ascii_part = re.sub(r"[^a-z0-9]+", "-", entity_id.casefold()).strip("-")
    digest = hashlib.sha256(entity_id.encode("utf-8")).hexdigest()[:8]
    prefix = ascii_part[:48].rstrip("-") or "entity"
    return f"{prefix}-{digest}"


def _inline_plain(text: str) -> str:
    safe = html.escape(text, quote=False)
    safe = re.sub(r"\*\*([^*\n]+)\*\*", r"<strong>\1</strong>", safe)
    safe = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", safe)
    return safe


def render_inline(
    text: str,
    names: dict[str, list[Entity]],
    slugs: dict[str, str],
    link_for: Callable[[str], str],
    current_id: str = "",
) -> str:
    """Render a deliberately small, escaped Markdown/Obsidian inline subset."""

    rendered: list[str] = []
    cursor = 0
    for match in INLINE_TOKEN_RE.finditer(text):
        rendered.append(_inline_plain(text[cursor : match.start()]))
        code, target, heading, alias, markdown_label, markdown_url = match.groups()
        if code is not None:
            rendered.append(f"<code>{html.escape(code)}</code>")
        elif target is not None:
            label = alias or target
            matches = resolve_entity_ref(target, names)
            if len(matches) == 1:
                target_id = scalar_text(matches[0].data.get("id"))
                fragment = f"#{quote(_slug_fragment(heading))}" if heading else ""
                href = fragment if target_id == current_id and fragment else link_for(slugs[target_id]) + fragment
                rendered.append(
                    f'<a class="wiki-link" href="{html.escape(href, quote=True)}">{_inline_plain(label)}</a>'
                )
            else:
                rendered.append(f'<span class="unresolved-link">{_inline_plain(label)}</span>')
        else:
            rendered.append(
                f'<a href="{html.escape(markdown_url, quote=True)}" rel="noreferrer">'
                f"{_inline_plain(markdown_label)}</a>"
            )
        cursor = match.end()
    rendered.append(_inline_plain(text[cursor:]))
    return "".join(rendered)


def _split_table_row(line: str) -> list[str]:
    value = line.strip().strip("|")
    return [cell.strip() for cell in value.split("|")]


def render_markdown(
    body: str,
    names: dict[str, list[Entity]],
    slugs: dict[str, str],
    link_for: Callable[[str], str],
    current_id: str,
    title: str,
) -> str:
    """Render the repository's body Markdown without allowing raw HTML."""

    lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    output: list[str] = []
    index = 0
    skipped_title = False

    def inline(value: str) -> str:
        return render_inline(value, names, slugs, link_for, current_id)

    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue

        if line.strip().startswith("```"):
            language = line.strip()[3:].strip()
            code_lines: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            index += 1 if index < len(lines) else 0
            class_name = f' class="language-{html.escape(language, quote=True)}"' if language else ""
            output.append(f"<pre><code{class_name}>{html.escape(chr(10).join(code_lines))}</code></pre>")
            continue

        heading_match = HEADING_RE.match(line)
        if heading_match:
            level = len(heading_match.group(1))
            heading_text = heading_match.group(2).strip()
            if level == 1 and not skipped_title and _plain_text(heading_text) == _plain_text(title):
                skipped_title = True
                index += 1
                continue
            rendered_level = min(max(level, 2), 4)
            anchor = _slug_fragment(_plain_text(heading_text))
            display_heading = HEADING_LABELS.get(heading_text, heading_text)
            output.append(f'<h{rendered_level} id="{html.escape(anchor, quote=True)}">{inline(display_heading)}</h{rendered_level}>')
            index += 1
            continue

        if line.strip() in {"---", "***", "___"}:
            output.append("<hr>")
            index += 1
            continue

        if index + 1 < len(lines) and "|" in line and TABLE_SEPARATOR_RE.match(lines[index + 1]):
            headers = _split_table_row(line)
            index += 2
            rows: list[list[str]] = []
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                rows.append(_split_table_row(lines[index]))
                index += 1
            head_html = "".join(f"<th scope=\"col\">{inline(cell)}</th>" for cell in headers)
            body_html = "".join(
                "<tr>" + "".join(f"<td>{inline(cell)}</td>" for cell in row) + "</tr>" for row in rows
            )
            output.append(
                '<div class="table-wrap" tabindex="0"><table><thead><tr>'
                + head_html
                + "</tr></thead><tbody>"
                + body_html
                + "</tbody></table></div>"
            )
            continue

        unordered = LIST_RE.match(line)
        ordered = ORDERED_LIST_RE.match(line)
        if unordered or ordered:
            tag = "ul" if unordered else "ol"
            items: list[str] = []
            while index < len(lines):
                match = LIST_RE.match(lines[index]) if tag == "ul" else ORDERED_LIST_RE.match(lines[index])
                if not match:
                    break
                items.append(f"<li>{inline(match.group(1))}</li>")
                index += 1
            output.append(f"<{tag}>" + "".join(items) + f"</{tag}>")
            continue

        if line.lstrip().startswith(">"):
            quote_lines: list[str] = []
            while index < len(lines) and lines[index].lstrip().startswith(">"):
                quote_lines.append(lines[index].lstrip()[1:].lstrip())
                index += 1
            output.append(f"<blockquote><p>{inline(' '.join(quote_lines))}</p></blockquote>")
            continue

        paragraph: list[str] = [line.strip()]
        index += 1
        while index < len(lines) and lines[index].strip():
            candidate = lines[index]
            if (
                HEADING_RE.match(candidate)
                or candidate.strip().startswith("```")
                or candidate.strip() in {"---", "***", "___"}
                or LIST_RE.match(candidate)
                or ORDERED_LIST_RE.match(candidate)
                or candidate.lstrip().startswith(">")
                or (index + 1 < len(lines) and "|" in candidate and TABLE_SEPARATOR_RE.match(lines[index + 1]))
            ):
                break
            paragraph.append(candidate.strip())
            index += 1
        output.append(f"<p>{inline(' '.join(paragraph))}</p>")

    return "\n".join(output)


def _plain_text(value: str) -> str:
    value = re.sub(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]", lambda m: m.group(2) or m.group(1), value)
    value = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", value)
    value = re.sub(r"[`*_>#~-]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _summary(entity: Entity) -> str:
    data = entity.data
    candidates = (
        data.get("holding_summary"),
        data.get("conclusion"),
        data.get("definition"),
        data.get("issue"),
    )
    for candidate in candidates:
        text = _plain_text(scalar_text(candidate))
        if text:
            return text
    body = re.sub(r"^#{1,6}\s+.+$", "", entity.body, flags=re.M)
    return _truncate_summary(_plain_text(body))


def _truncate_summary(text: str, limit: int = 240) -> str:
    if len(text) <= limit:
        return text
    window = text[: limit + 1]
    sentence_ends = [match.end() for match in re.finditer(r"[.!?。](?:\s|$)", window)]
    if sentence_ends and sentence_ends[-1] >= limit // 2:
        return window[: sentence_ends[-1]].strip()
    shortened = window[:limit].rsplit(" ", 1)[0].rstrip(" ,;:")
    if not shortened:
        shortened = window[:limit].rstrip(" ,;:")
    return shortened + "…"


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


def _normalise_search(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold().replace("ㆍ", "·")
    return re.sub(r"[\s·.,:;()\[\]{}'\"/_-]+", "", value)


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
        search_parts = [entity_id, scalar_text(data.get("title")), summary, entity.body]
        for field in SEARCH_FIELDS:
            search_parts.extend(_flatten(data.get(field)))
        search_text = " ".join(part for part in search_parts if part)
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
                "searchText": search_text,
                "searchNormalised": _normalise_search(search_text),
                "url": f"entities/{slugs[entity_id]}/",
            }
        )
    return records


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
    search_core_url = html.escape(f"{asset_prefix}search-core.js?v={ASSET_VERSION}", quote=True)
    script_url = html.escape(f"{asset_prefix}app.js?v={ASSET_VERSION}", quote=True)
    script = (
        f'<script defer src="{search_core_url}"></script>\n  <script defer src="{script_url}"></script>'
        if include_app
        else ""
    )
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


def _feature_list(title: str, records: Iterable[dict[str, Any]], description: str) -> str:
    items = "".join(
        f'<li><a href="{html.escape(item["url"], quote=True)}"><span>{html.escape(item["number"])}</span>'
        f'<strong>{html.escape(item["title"])}</strong><small>{html.escape(item["dateDisplay"])}</small></a></li>'
        for item in records
    )
    return f"""<section class="feature-column">
  <header><h3>{html.escape(title)}</h3><p>{html.escape(description)}</p></header>
  <ol>{items}</ol>
</section>"""


def _home_page(
    records: list[dict[str, Any]],
    counts: Counter[str],
    status_counts: Counter[str],
    legal_counts: Counter[str],
    as_of: str,
    site_url: str,
    repository_url: str,
) -> str:
    trusted = [
        item
        for item in records
        if item["status"] == "verified" and item["legalStatus"] == "current" and item["effectiveFrom"] <= as_of <= item["effectiveTo"]
    ]
    trusted.sort(key=lambda item: item["sortDate"], reverse=True)
    initial = trusted[:18]
    latest_cases = sorted(
        (item for item in trusted if item["type"] == "case"), key=lambda item: item["sortDate"], reverse=True
    )[:4]
    current_rules = sorted(
        (item for item in trusted if item["type"] == "rule"), key=lambda item: item["sortDate"], reverse=True
    )[:4]
    future = sorted(
        (item for item in records if item["legalStatus"] == "future" and item["status"] == "verified"),
        key=lambda item: item["effectiveFrom"],
    )[:4]
    type_buttons = [f'<button type="button" class="type-filter is-active" data-type="all" aria-pressed="true">전체 <span>{len(records)}</span></button>']
    for entity_type in sorted(counts, key=lambda value: TYPE_ORDER.get(value, 99)):
        type_buttons.append(
            f'<button type="button" class="type-filter" data-type="{html.escape(entity_type, quote=True)}" aria-pressed="false">'
            f'{html.escape(TYPE_LABELS.get(entity_type, entity_type))} <span>{counts[entity_type]}</span></button>'
        )
    initial_cards = "".join(_record_card(item) for item in initial)
    formatted_as_of = html.escape(_format_date(as_of))
    body = f"""{_site_header('./', repository_url)}
<main id="main">
  <section class="hero" aria-labelledby="hero-title">
    <div class="hero__copy">
      <p class="section-label">대한민국 임금법 지식베이스</p>
      <h1 id="hero-title">판례와 규칙을<br>한 흐름으로 읽습니다.</h1>
      <p class="hero__description">법령, 판례, 행정해석과 사실유형을 근거·관계·적용 시점에 따라 탐색할 수 있습니다. 기본 검색은 검증된 현행 자료만 보여줍니다.</p>
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

  <section class="featured" aria-labelledby="featured-title">
    <div class="section-heading"><p class="section-label">시점별 길잡이</p><h2 id="featured-title">지금 읽을 문서</h2></div>
    <div class="featured__grid">
      {_feature_list('현행 핵심 규칙', current_rules, '현재 적용되는 검증된 판단 규칙')}
      {_feature_list('최신 판례', latest_cases, '선고일이 가장 최근인 검증된 현행 판례')}
      {_feature_list('장래 적용', future, '시행 전 반드시 날짜를 확인할 자료')}
    </div>
  </section>

  <section class="explorer" id="explore" aria-labelledby="explore-title" data-index-url="assets/entities.json?v={ASSET_VERSION}" data-default-date="{html.escape(as_of, quote=True)}">
    <div class="section-heading section-heading--split">
      <div><p class="section-label">전체 지식베이스</p><h2 id="explore-title">문서 탐색</h2></div>
      <p class="result-status" id="result-status" aria-live="polite">검증된 현행 문서 {len(trusted)}개</p>
    </div>
    <form class="search-panel" id="search-form" role="search">
      <label for="search-input">판례·규칙·법령 검색</label>
      <div class="search-row">
        <input id="search-input" name="q" type="search" autocomplete="off" placeholder="사건번호, 임금 유형, 판단 기준을 입력하세요">
        <button type="button" id="clear-search">검색어 지우기</button>
      </div>
      <p>사건번호의 공백과 가운뎃점 차이는 검색 결과에 영향을 주지 않습니다.</p>
    </form>

    <div class="type-filters" aria-label="문서 유형 필터">{''.join(type_buttons)}</div>

    <div class="filter-grid">
      <label>편집 상태
        <select id="status-filter">
          <option value="verified" selected>검증됨</option>
          <option value="review">검토 중</option>
          <option value="draft">초안</option>
          <option value="all">전체</option>
        </select>
      </label>
      <label>법적 상태
        <select id="legal-filter">
          <option value="current" selected>현행</option>
          <option value="future">장래 적용</option>
          <option value="superseded">대체됨</option>
          <option value="overruled">판례 변경됨</option>
          <option value="historical">역사적 자료</option>
          <option value="all">전체</option>
        </select>
      </label>
      <label>기준 시점
        <input id="date-filter" type="date" value="{html.escape(as_of, quote=True)}" aria-describedby="date-filter-note">
      </label>
      <label>정렬
        <select id="sort-filter">
          <option value="date">최신순</option>
          <option value="relevance">관련도순</option>
          <option value="authority">권위순</option>
          <option value="title">제목순</option>
        </select>
      </label>
      <label class="check-label"><input id="effective-filter" type="checkbox" checked> 기준 시점에 유효한 문서만</label>
      <div class="filter-actions">
        <button type="button" id="reset-filters">기본값 복원</button>
        <button type="button" id="show-all">전체 문서 보기</button>
      </div>
      <p class="filter-note" id="date-filter-note">과거 기준일을 선택하면 당시 유효했던 대체·판례변경 문서를 포함하도록 법적 상태가 전체로 바뀝니다.</p>
    </div>

    <noscript><p class="notice">검색과 필터를 사용하려면 JavaScript가 필요합니다. 아래에는 검증된 현행 문서 일부가 표시됩니다.</p></noscript>
    <div class="results" id="results">{initial_cards}</div>
    <div class="load-more-wrap"><button type="button" id="load-more" hidden>더 보기</button></div>
    <div class="empty-state" id="empty-state" hidden><h3>조건에 맞는 문서가 없습니다.</h3><p>검색어를 줄이거나 편집·법적 상태 필터를 변경해 보세요.</p></div>
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
) -> list[tuple[Entity, str, str]]:
    data = entity.data
    source_id = scalar_text(data.get("id"))
    found: dict[tuple[str, str], tuple[Entity, str, str]] = {}
    targets_with_typed_relation: set[str] = set()

    def add(target: Entity, relation: str, note: str = "", *, fallback: bool = False) -> None:
        target_id = scalar_text(target.data.get("id"))
        if not target_id or target_id == source_id or (fallback and target_id in targets_with_typed_relation):
            return
        key = (target_id, relation)
        if key in found:
            previous_target, previous_relation, previous_note = found[key]
            if note and note not in previous_note:
                combined_note = " / ".join(value for value in (previous_note, note) if value)
                found[key] = (previous_target, previous_relation, combined_note)
            return
        found[key] = (target, relation, note)
        if not fallback:
            targets_with_typed_relation.add(target_id)

    for relation in as_list(data.get("relations")):
        if isinstance(relation, dict):
            target = by_id.get(scalar_text(relation.get("target_id")))
            if target:
                add(target, scalar_text(relation.get("relation_type")) or "related_to", scalar_text(relation.get("note")))
    primary = by_id.get(scalar_text(data.get("primary_authority_id")))
    if primary:
        add(primary, "has_primary_authority", fallback=True)
    for authority_id in as_list(data.get("authority_ids")):
        target = by_id.get(scalar_text(authority_id))
        if target:
            add(target, "has_authority", fallback=True)
    for field in RELATED_FIELDS:
        for target_name in wiki_targets(data.get(field)):
            matches = resolve_entity_ref(target_name, names)
            if len(matches) == 1:
                add(matches[0], "related_to", fallback=True)
    return sorted(
        found.values(),
        key=lambda item: (
            TYPE_ORDER.get(scalar_text(item[0].data.get("entity_type")), 99),
            scalar_text(item[0].data.get("title")).casefold(),
            item[1],
        ),
    )


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


def _entity_page(
    entity: Entity,
    record: dict[str, Any],
    by_id: dict[str, Entity],
    names: dict[str, list[Entity]],
    slugs: dict[str, str],
    site_url: str,
    repository_url: str,
    branch: str,
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
    related_html = "".join(
        f'<li><a href="../{slugs[scalar_text(target.data.get("id"))]}/">'
        f'<span>{html.escape(TYPE_LABELS.get(scalar_text(target.data.get("entity_type")), scalar_text(target.data.get("entity_type"))))}</span>'
        f'<strong>{html.escape(scalar_text(target.data.get("title")))}</strong>'
        f'<small>{html.escape(RELATION_LABELS.get(relation, relation))}</small></a>'
        + (f'<p>{html.escape(note)}</p>' if note else "")
        + "</li>"
        for target, relation, note in related
    )
    metadata_html = "".join(
        f"<div><dt>{html.escape(label)}</dt><dd>{html.escape(value)}</dd></div>" for label, value in _metadata_rows(data)
    )
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
        evidence_items.append(
            f"""<li>
  <div class="evidence__meta"><span>{html.escape(source_id)}</span><span>{html.escape(locator)}</span></div>
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
<main id="main">
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
      <aside class="document-meta" aria-label="문서 메타데이터"><dl>{metadata_html}</dl></aside>
    </header>

    <div class="document-grid">
      <div class="document-index" aria-hidden="true">{html.escape(record['number'])}</div>
      <div class="prose">{body_html}</div>
      <aside class="relations" aria-labelledby="relations-title">
        <div class="aside-heading"><span>{len(related):02d}</span><h2 id="relations-title">연결 문서</h2></div>
        <ul>{related_html}</ul>
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
<main id="main" class="about">
  <header class="about-hero"><p class="section-label">데이터 안내</p><h1>무엇을, 어떤 기준으로<br>보여주는가</h1><p>Wage Wiki는 Markdown 원본의 구조화된 메타데이터와 본문을 빌드 시 정적 HTML로 변환합니다. 웹 페이지에는 원문 PDF·HTML을 복제하지 않고 공식 외부 주소만 연결합니다.</p></header>
  <section class="about-grid" aria-labelledby="coverage-title">
    <div class="section-heading"><p class="section-label">기준일 {html.escape(_format_date(as_of))}</p><h2 id="coverage-title">수록 범위</h2></div>
    <div class="table-wrap"><table><thead><tr><th>문서 유형</th><th>건수</th></tr></thead><tbody>{type_rows}</tbody></table></div>
    <div class="table-wrap"><table><thead><tr><th>편집 상태</th><th>건수</th></tr></thead><tbody>{status_rows}</tbody></table></div>
    <div class="table-wrap"><table><thead><tr><th>법적 상태</th><th>건수</th></tr></thead><tbody>{legal_rows}</tbody></table></div>
  </section>
  <section class="about-copy">
    <h2>두 가지 상태를 분리합니다.</h2>
    <p><strong>편집 상태</strong>는 문서가 초안, 검토 중, 검증됨 중 어디에 있는지를 뜻합니다. <strong>법적 상태</strong>는 법리가 현행인지, 장래 적용인지, 대체되거나 판례 변경된 것인지를 뜻합니다. 검증된 문서라도 역사적 법리일 수 있으므로 두 상태를 함께 확인해야 합니다.</p>
    <h2>기본 검색은 시점 안전성을 우선합니다.</h2>
    <p>첫 화면은 기준일에 유효한 검증된 현행 문서만 표시합니다. 사용자가 편집 상태, 법적 상태, 기준 시점을 바꾸면 장래 자료와 과거 법리도 탐색할 수 있습니다.</p>
    <h2>근거와 관계를 함께 제공합니다.</h2>
    <p>판단 요약만 제시하지 않고 출처 ID, 원문 위치, 짧은 발췌, 검증일과 공식 외부 주소를 표시합니다. 문서 사이의 확립·적용·해석·대체 관계도 상세 화면에서 확인할 수 있습니다.</p>
    <h2>정적 사이트로 운영합니다.</h2>
    <p>사이트는 GitHub Actions에서 다시 생성되어 GitHub Pages로 배포됩니다. 서버, 사용자 계정, 광고·분석 스크립트를 사용하지 않으며 검색은 브라우저 안에서만 처리됩니다.</p>
  </section>
  <section class="disclaimer"><h2>책임 범위</h2><p>이 사이트는 연구와 정보 제공을 위한 자료입니다. 실제 사건에는 사실관계, 적용 시점, 단체협약·취업규칙 등 추가 요소가 영향을 줄 수 있으므로 필요한 경우 전문가의 검토를 받으세요.</p><a class="text-link" href="../#explore">문서 탐색으로 돌아가기</a></section>
</main>
<footer class="site-footer"><p>Wage Wiki · 전체 {len(records)}개 문서</p><p><a href="{html.escape(repository_url, quote=True)}">GitHub 저장소</a></p></footer>"""
    return _document(
        title=f"데이터 안내 | {SITE_TITLE}",
        description="Wage Wiki의 수록 범위, 편집·법적 상태, 검색 기준과 근거 표시 방법",
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
    body = f"""{_site_header(home_url, repository_url)}<main id="main" class="not-found"><p class="error-code">404</p><h1>페이지를 찾을 수 없습니다.</h1><p>주소가 변경되었거나 존재하지 않는 문서입니다.</p><a class="text-link" href="{html.escape(home_url, quote=True)}#explore">전체 문서 검색</a></main>"""
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
    for required in ("styles.css", "search-core.js", "app.js", "favicon.svg"):
        if not (asset_source / required).is_file():
            raise RuntimeError(f"missing web asset: {asset_source / required}")
    asset_digest = hashlib.sha256()
    for asset_name in ("styles.css", "search-core.js", "app.js", "favicon.svg"):
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

    if output.exists():
        shutil.rmtree(output)
    (output / "assets").mkdir(parents=True)
    shutil.copy2(asset_source / "styles.css", output / "assets" / "styles.css")
    shutil.copy2(asset_source / "search-core.js", output / "assets" / "search-core.js")
    shutil.copy2(asset_source / "app.js", output / "assets" / "app.js")
    shutil.copy2(asset_source / "favicon.svg", output / "assets" / "favicon.svg")
    (output / "index.html").write_text(
        _home_page(records, counts, status_counts, legal_counts, as_of, site_url, repository_url),
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
