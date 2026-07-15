#!/usr/bin/env python3
"""Render the escaped Markdown/Obsidian subset used by the static site."""

from __future__ import annotations

import html
import re
from typing import Callable
from urllib.parse import quote

from kg_common import Entity, resolve_entity_ref, scalar_text
from site_mermaid import render_mermaid_flowchart


HEADING_LABELS = {
    "2026 Case Update": "2026년 판례 업데이트",
    "Administrative Position": "행정해석상 입장",
    "Application": "적용",
    "Application Order": "적용 순서",
    "Article 44-4": "제44조의4",
    "Authority": "근거 권위",
    "Authority Note": "권위 범위",
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
    "Notes": "적용상 주의",
    "Operative Changes": "주요 개정 내용",
    "Operative Terms": "적용 조항",
    "Origin": "기원",
    "Performance Pay Minimum Guarantee": "성과급 최소보장",
    "Positions": "견해",
    "Practical Application": "실무 적용",
    "Practical Assessment": "실무 판단",
    "Practical Notes": "실무상 주의",
    "Provision": "조문",
    "Reasoning": "판단 이유",
    "Revision Notes": "개정 내역",
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
    "Version Note": "버전 정보",
}

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
LIST_RE = re.compile(r"^\s*[-*+]\s+(.+)$")
ORDERED_LIST_RE = re.compile(r"^\s*\d+[.)]\s+(.+)$")
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")
INLINE_TOKEN_RE = re.compile(
    r"`([^`\n]+)`"
    r"|\[\[([^\]|#]+)(?:#([^\]|]+))?(?:\|([^\]]+))?\]\]"
    r"|\[([^\]]+)\]\((https?://[^\s)]+)\)"
)

def _slug_fragment(value: str) -> str:
    value = re.sub(r"[`*_~]", "", value.strip().lower())
    value = re.sub(r"[^0-9a-z가-힣]+", "-", value, flags=re.I)
    return value.strip("-") or "section"

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
    diagram_index = 0

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
            if language.casefold() == "mermaid":
                diagram_index += 1
                output.append(
                    render_mermaid_flowchart(chr(10).join(code_lines), f"{current_id}-{diagram_index}")
                )
                continue
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
            return _truncate_summary(text, limit=160)
    body_lines = entity.body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    paragraph: list[str] = []
    in_code = False
    for line in body_lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            if paragraph:
                break
            continue
        if in_code:
            continue
        if not stripped:
            if paragraph:
                break
            continue
        if (
            HEADING_RE.match(line)
            or stripped in {"---", "***", "___"}
            or TABLE_SEPARATOR_RE.match(line)
            or stripped.startswith("|")
            or LIST_RE.match(line)
            or ORDERED_LIST_RE.match(line)
        ):
            if paragraph:
                break
            continue
        paragraph.append(stripped.lstrip("> "))

    text = _plain_text(" ".join(paragraph))
    if not text:
        body = re.sub(r"^#{1,6}\s+.+$", "", entity.body, flags=re.M)
        text = _plain_text(body)
    return _truncate_summary(text, limit=160)


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
