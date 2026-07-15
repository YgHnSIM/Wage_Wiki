#!/usr/bin/env python3
"""Render the escaped Markdown/Obsidian subset used by the static site."""

from __future__ import annotations

import html
import re
from typing import Callable
from urllib.parse import quote

from claim_contract import (
    CLAIM_ID_RE,
    body_plain_text,
    HEADING_RE,
    LIST_RE,
    ORDERED_LIST_RE,
    STANDALONE_CLAIM_MARKER_RE,
    TABLE_SEPARATOR_RE,
    fence_closes,
    fence_spec,
    heading_fragment,
    is_document_title_heading,
    markdown_plain_text,
    split_claim_marker,
    strip_fenced_blocks,
)
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

INLINE_TOKEN_RE = re.compile(
    r"`([^`\n]+)`"
    r"|\[\[([^\]|#]+)(?:#([^\]|]+))?(?:\|([^\]]+))?\]\]"
    r"|\[([^\]]+)\]\((https?://[^\s)]+)\)"
)

def _slug_fragment(value: str) -> str:
    return heading_fragment(value)

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


def _block_id_attribute(claim_id: str) -> str:
    return f' id="{html.escape(claim_id, quote=True)}"' if claim_id else ""

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
    standalone_target: int | None = None
    standalone_target_has_id = False

    def inline(value: str) -> str:
        return render_inline(value, names, slugs, link_for, current_id)

    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue

        opener = fence_spec(line)
        if opener is not None:
            fence_character, fence_length, language = opener
            code_lines: list[str] = []
            index += 1
            while index < len(lines) and not fence_closes(
                lines[index],
                fence_character,
                fence_length,
            ):
                code_lines.append(lines[index])
                index += 1
            index += 1 if index < len(lines) else 0
            if language.casefold() == "mermaid":
                diagram_index += 1
                output.append(
                    render_mermaid_flowchart(chr(10).join(code_lines), f"{current_id}-{diagram_index}")
                )
                standalone_target = None
                continue
            class_name = f' class="language-{html.escape(language, quote=True)}"' if language else ""
            output.append(f"<pre><code{class_name}>{html.escape(chr(10).join(code_lines))}</code></pre>")
            standalone_target = None
            continue

        standalone_claim = STANDALONE_CLAIM_MARKER_RE.fullmatch(line)
        if standalone_claim and CLAIM_ID_RE.fullmatch(standalone_claim.group(1)):
            claim_id = standalone_claim.group(1)
            if standalone_target is not None and not standalone_target_has_id:
                output[standalone_target] = re.sub(
                    r"^<([a-z][a-z0-9-]*)",
                    lambda match: f'<{match.group(1)} id="{html.escape(claim_id, quote=True)}"',
                    output[standalone_target],
                    count=1,
                )
            standalone_target = None
            standalone_target_has_id = False
            index += 1
            continue

        heading_match = HEADING_RE.match(line)
        if heading_match:
            level = len(heading_match.group(1))
            heading_text = heading_match.group(2).strip()
            if is_document_title_heading(level, heading_text, title, skipped_title):
                skipped_title = True
                index += 1
                continue
            rendered_level = min(max(level, 2), 4)
            anchor = _slug_fragment(_plain_text(heading_text))
            display_heading = HEADING_LABELS.get(heading_text, heading_text)
            output.append(f'<h{rendered_level} id="{html.escape(anchor, quote=True)}">{inline(display_heading)}</h{rendered_level}>')
            standalone_target = None
            index += 1
            continue

        if line.strip() in {"---", "***", "___"}:
            output.append("<hr>")
            standalone_target = None
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
            standalone_target = None
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
                item_text, claim_id = split_claim_marker(match.group(1))
                items.append(f"<li{_block_id_attribute(claim_id)}>{inline(item_text)}</li>")
                index += 1
            output.append(f"<{tag}>" + "".join(items) + f"</{tag}>")
            standalone_target = None
            continue

        if line.lstrip().startswith(">"):
            quote_lines: list[str] = []
            while index < len(lines) and lines[index].lstrip().startswith(">"):
                quote_lines.append(lines[index].lstrip()[1:].lstrip())
                index += 1
            quote_text, claim_id = split_claim_marker(" ".join(quote_lines))
            output.append(f"<blockquote{_block_id_attribute(claim_id)}><p>{inline(quote_text)}</p></blockquote>")
            standalone_target = len(output) - 1
            standalone_target_has_id = bool(claim_id)
            continue

        paragraph: list[str] = [line.strip()]
        index += 1
        while index < len(lines) and lines[index].strip():
            candidate = lines[index]
            candidate_marker = STANDALONE_CLAIM_MARKER_RE.fullmatch(candidate)
            if candidate_marker and CLAIM_ID_RE.fullmatch(candidate_marker.group(1)):
                paragraph.append(candidate.strip())
                index += 1
                break
            if (
                HEADING_RE.match(candidate)
                or fence_spec(candidate) is not None
                or candidate.strip() in {"---", "***", "___"}
                or LIST_RE.match(candidate)
                or ORDERED_LIST_RE.match(candidate)
                or candidate.lstrip().startswith(">")
                or (index + 1 < len(lines) and "|" in candidate and TABLE_SEPARATOR_RE.match(lines[index + 1]))
            ):
                break
            paragraph.append(candidate.strip())
            index += 1
        paragraph_text, claim_id = split_claim_marker(" ".join(paragraph))
        output.append(f"<p{_block_id_attribute(claim_id)}>{inline(paragraph_text)}</p>")
        standalone_target = len(output) - 1
        standalone_target_has_id = bool(claim_id)

    return "\n".join(output)


def _plain_text(value: str) -> str:
    return markdown_plain_text(value)


def _body_plain_text(value: str) -> str:
    return body_plain_text(value)


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
    fence: tuple[str, int] | None = None
    for line in body_lines:
        stripped = line.strip()
        if fence is not None:
            if fence_closes(line, *fence):
                fence = None
            if paragraph:
                break
            continue
        opener = fence_spec(line)
        if opener is not None:
            fence = opener[:2]
            if paragraph:
                break
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

    text = _body_plain_text(" ".join(paragraph))
    if not text:
        body = strip_fenced_blocks(entity.body)
        body = re.sub(r"^#{1,6}\s+.+$", "", body, flags=re.M)
        text = _body_plain_text(body)
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
