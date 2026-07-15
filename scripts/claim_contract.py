#!/usr/bin/env python3
"""Shared contract for document-local Obsidian claim block identifiers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from kg_common import as_list, scalar_text


CLAIM_ID_PATTERN = r"^[a-z][a-z0-9-]{0,63}$"
CLAIM_ID_RE = re.compile(CLAIM_ID_PATTERN)
TRAILING_CLAIM_MARKER_RE = re.compile(r"(?:^|\s)\^([^\s^]+)\s*$")
VALID_TRAILING_CLAIM_MARKER_RE = re.compile(
    r"(?:^|\s)\^([a-z][a-z0-9-]{0,63})\s*$"
)
STANDALONE_CLAIM_MARKER_RE = re.compile(r"\s*\^([^\s^]+)\s*")
FENCE_OPEN_RE = re.compile(r"^\s*(?P<fence>`{3,}|~{3,})(?P<info>.*)$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
LIST_RE = re.compile(r"^\s*[-*+]\s+(.+)$")
ORDERED_LIST_RE = re.compile(r"^\s*\d+[.)]\s+(.+)$")
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")
DOCUMENT_MAIN_FRAGMENT_ID = "main"
DECISION_PATH_FRAGMENT_ID = "decision-path-title"
EVIDENCE_FRAGMENT_ID = "evidence-title"
SOURCES_FRAGMENT_ID = "sources-title"
RELATIONS_FRAGMENT_ID = "relations-title"
FIXED_PAGE_FRAGMENT_IDS = frozenset(
    {
        DOCUMENT_MAIN_FRAGMENT_ID,
        DECISION_PATH_FRAGMENT_ID,
        EVIDENCE_FRAGMENT_ID,
        SOURCES_FRAGMENT_ID,
        RELATIONS_FRAGMENT_ID,
    }
)


@dataclass(frozen=True)
class ClaimAnchor:
    claim_id: str
    line: int
    text: str


@dataclass(frozen=True)
class ClaimProblem:
    severity: str
    code: str
    message: str
    field: str


def evidence_claim_ids(evidence: Any) -> list[str]:
    """Return supported claim IDs in stable first-occurrence order."""

    result: list[str] = []
    seen: set[str] = set()
    for record in as_list(evidence):
        if not isinstance(record, dict):
            continue
        for raw in as_list(record.get("supports")):
            claim_id = scalar_text(raw)
            if claim_id and claim_id not in seen:
                result.append(claim_id)
                seen.add(claim_id)
    return result


def global_claim_id(entity_id: str, claim_id: str) -> str:
    """Qualify a document-local claim for graph exports."""

    return f"claim:{quote(entity_id, safe='')}#{quote(claim_id, safe='')}"


def global_evidence_id(entity_id: str, evidence_id: str) -> str:
    """Qualify a document-local evidence record for graph references."""

    return f"evidence:{quote(entity_id, safe='')}#{quote(evidence_id, safe='')}"


def global_source_id(source_id: str) -> str:
    """Place registered raw sources in a graph namespace distinct from entities."""

    return f"source:{quote(source_id, safe='')}"


def markdown_plain_text(value: str) -> str:
    """Normalize Markdown markup without damaging literal domain punctuation."""

    value = re.sub(r"<br\s*/?>", " ", value, flags=re.I)
    value = re.sub(
        r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]",
        lambda match: match.group(2) or match.group(1),
        value,
    )
    value = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", value)
    value = re.sub(r"`([^`\n]+)`", r"\1", value)
    value = re.sub(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1", r"\2", value)
    value = re.sub(r"~~(?=\S)(.+?)(?<=\S)~~", r"\1", value)
    value = re.sub(r"(?<!\*)\*(?=\S)(.+?)(?<=\S)\*(?!\*)", r"\1", value)
    value = re.sub(
        r"(?<![\w_])_(?=\S)(.+?)(?<=\S)_(?![\w_])",
        r"\1",
        value,
    )
    value = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", value)
    value = re.sub(r"(?m)^\s*>\s?", "", value)
    return re.sub(r"\s+", " ", value).strip()


def heading_fragment(value: str) -> str:
    """Return the site renderer's deterministic Markdown heading fragment."""

    value = markdown_plain_text(value)
    value = re.sub(r"[`*_~]", "", value.strip().lower())
    value = re.sub(r"[^0-9a-z가-힣]+", "-", value, flags=re.I)
    return value.strip("-") or "section"


def is_document_title_heading(
    level: int,
    heading_text: str,
    title: str,
    title_already_skipped: bool,
) -> bool:
    """Mirror the renderer rule that suppresses one matching level-one title."""

    return (
        level == 1
        and not title_already_skipped
        and markdown_plain_text(heading_text) == markdown_plain_text(title)
    )


def rendered_heading_fragments(body: str, title: str) -> set[str]:
    """Return only heading IDs that the body renderer will emit."""

    result: set[str] = set()
    fence: tuple[str, int] | None = None
    title_skipped = False
    for line in body.splitlines():
        if fence is not None:
            if fence_closes(line, *fence):
                fence = None
            continue
        opener = fence_spec(line)
        if opener is not None:
            fence = opener[:2]
            continue
        match = HEADING_RE.match(line)
        if not match:
            continue
        level = len(match.group(1))
        heading_text = match.group(2).strip()
        if is_document_title_heading(level, heading_text, title, title_skipped):
            title_skipped = True
            continue
        result.add(heading_fragment(heading_text))
    return result


def fence_spec(line: str) -> tuple[str, int, str] | None:
    """Return fence character, minimum closing length, and info string."""

    match = FENCE_OPEN_RE.match(line)
    if not match:
        return None
    marker = match.group("fence")
    return marker[0], len(marker), match.group("info").strip()


def fence_closes(line: str, character: str, minimum_length: int) -> bool:
    """Match CommonMark-style closing fences without accepting shorter runs."""

    return bool(re.fullmatch(rf"\s*{re.escape(character)}{{{minimum_length},}}\s*", line))


def split_claim_marker(value: str) -> tuple[str, str]:
    """Split a valid trailing claim marker from renderable block text."""

    match = VALID_TRAILING_CLAIM_MARKER_RE.search(value)
    if not match:
        return value, ""
    return value[: match.start()].rstrip(), match.group(1)


def _table_line_numbers(lines: list[str]) -> set[int]:
    result: set[int] = set()
    for index, line in enumerate(lines):
        if not TABLE_SEPARATOR_RE.match(line) or index == 0 or "|" not in lines[index - 1]:
            continue
        result.update({index, index - 1})
        cursor = index + 1
        while cursor < len(lines) and lines[cursor].strip() and "|" in lines[cursor]:
            result.add(cursor)
            cursor += 1
    return result


def _renderable_block_text(value: str) -> str:
    """Remove Markdown container syntax before checking claim content."""

    for pattern in (LIST_RE, ORDERED_LIST_RE):
        match = pattern.match(value)
        if match:
            return match.group(1).strip()
    stripped = value.strip()
    if stripped.startswith(">"):
        return stripped[1:].lstrip()
    return stripped


def _prose_block_kind(line: str, index: int, table_lines: set[int]) -> str:
    stripped = line.strip()
    if (
        not stripped
        or HEADING_RE.match(line)
        or LIST_RE.match(line)
        or ORDERED_LIST_RE.match(line)
        or index in table_lines
        or stripped in {"---", "***", "___"}
        or fence_spec(line) is not None
    ):
        return ""
    return "quote" if line.lstrip().startswith(">") else "paragraph"


def _scan_claim_anchors(body: str) -> tuple[tuple[ClaimAnchor, ...], tuple[tuple[int, str], ...]]:
    lines = body.splitlines()
    table_lines = _table_line_numbers(lines)
    anchors: list[ClaimAnchor] = []
    rejected: list[tuple[int, str]] = []
    fence: tuple[str, int] | None = None
    last_claimable: ClaimAnchor | None = None
    last_claimable_kind = ""
    last_claimed = False

    for index, line in enumerate(lines):
        line_number = index + 1
        if fence is not None:
            if fence_closes(line, *fence):
                fence = None
                last_claimable = None
                last_claimable_kind = ""
                last_claimed = False
            continue
        opener = fence_spec(line)
        if opener is not None:
            fence = opener[:2]
            last_claimable = None
            last_claimable_kind = ""
            last_claimed = False
            continue

        stripped = line.strip()
        if not stripped:
            continue
        marker = TRAILING_CLAIM_MARKER_RE.search(line)
        standalone = STANDALONE_CLAIM_MARKER_RE.fullmatch(line)
        if standalone:
            claim_id = standalone.group(1)
            if last_claimable is not None and not last_claimed:
                anchors.append(ClaimAnchor(claim_id, line_number, last_claimable.text))
                last_claimed = True
            else:
                rejected.append((line_number, claim_id))
            continue

        unsupported = (
            bool(HEADING_RE.match(line))
            or index in table_lines
            or stripped in {"---", "***", "___"}
        )
        if unsupported:
            if marker:
                rejected.append((line_number, marker.group(1)))
            last_claimable = None
            last_claimable_kind = ""
            last_claimed = False
            continue

        list_match = LIST_RE.match(line) or ORDERED_LIST_RE.match(line)
        if list_match:
            if marker:
                text, _ = split_claim_marker(list_match.group(1))
                anchors.append(ClaimAnchor(marker.group(1), line_number, text))
            last_claimable = None
            last_claimable_kind = ""
            last_claimed = bool(marker)
            continue

        text = _renderable_block_text(line[: marker.start()] if marker else line)
        if (
            marker
            and not text
            and line.lstrip().startswith(">")
            and last_claimable is not None
            and last_claimable_kind == "quote"
        ):
            text = last_claimable.text
        current_kind = _prose_block_kind(line, index, table_lines)
        next_kind = (
            _prose_block_kind(lines[index + 1], index + 1, table_lines)
            if index + 1 < len(lines)
            else ""
        )
        continues = bool(current_kind and current_kind == next_kind)
        if marker and continues:
            rejected.append((line_number, marker.group(1)))
        elif marker:
            anchors.append(ClaimAnchor(marker.group(1), line_number, text))
        last_claimable = ClaimAnchor("", line_number, text)
        last_claimable_kind = current_kind
        last_claimed = bool(marker and not continues)
    return tuple(anchors), tuple(rejected)


def claim_anchors(body: str) -> tuple[ClaimAnchor, ...]:
    """Extract only markers that every body consumer can render as fragments."""

    anchors, _ = _scan_claim_anchors(body)
    return anchors


def resolved_claim_ids(data: dict[str, Any], body: str) -> set[str]:
    """Return unique, renderable claim fragments outside every reserved namespace."""

    grouped: dict[str, list[ClaimAnchor]] = {}
    for anchor in claim_anchors(body):
        grouped.setdefault(anchor.claim_id, []).append(anchor)
    reserved = rendered_heading_fragments(body, scalar_text(data.get("title"))) | FIXED_PAGE_FRAGMENT_IDS
    return {
        claim_id
        for claim_id, matches in grouped.items()
        if CLAIM_ID_RE.fullmatch(claim_id)
        and len(matches) == 1
        and bool(matches[0].text)
        and claim_id not in reserved
    }


def strip_claim_markers(body: str) -> str:
    """Remove renderable block markers while preserving inline literal references."""

    anchors, _ = _scan_claim_anchors(body)
    accepted_lines = {
        anchor.line for anchor in anchors if CLAIM_ID_RE.fullmatch(anchor.claim_id)
    }
    lines = body.splitlines()
    for line_number in accepted_lines:
        lines[line_number - 1] = VALID_TRAILING_CLAIM_MARKER_RE.sub(
            "",
            lines[line_number - 1],
        ).rstrip()
    return "\n".join(lines)


def strip_fenced_blocks(body: str) -> str:
    """Remove complete fenced code blocks using the shared fence boundary rules."""

    result: list[str] = []
    fence: tuple[str, int] | None = None
    for line in body.splitlines():
        if fence is not None:
            if fence_closes(line, *fence):
                fence = None
            continue
        opener = fence_spec(line)
        if opener is not None:
            fence = opener[:2]
            continue
        result.append(line)
    return "\n".join(result)


def body_plain_text(body: str) -> str:
    """Return marker-free plain text shared by site and search consumers."""

    return markdown_plain_text(strip_claim_markers(body))


def validate_claim_anchors(
    data: dict[str, Any],
    body: str,
    *,
    require_anchors: bool = False,
) -> tuple[ClaimProblem, ...]:
    """Validate formats always and resolution only after rollout is enabled."""

    supported = evidence_claim_ids(data.get("evidence"))
    anchors, rejected = _scan_claim_anchors(body)
    problems: list[ClaimProblem] = []
    by_id: dict[str, list[ClaimAnchor]] = {}
    for anchor in anchors:
        by_id.setdefault(anchor.claim_id, []).append(anchor)
        if not CLAIM_ID_RE.fullmatch(anchor.claim_id):
            problems.append(
                ClaimProblem(
                    "high",
                    "CLAIM_ID_INVALID",
                    f"claim block ID contains unsupported characters: {anchor.claim_id}",
                    f"body:{anchor.line}",
                )
            )
        if not anchor.text:
            problems.append(
                ClaimProblem(
                    "high",
                    "CLAIM_BLOCK_EMPTY",
                    f"claim block has no text: {anchor.claim_id}",
                    f"body:{anchor.line}",
                )
            )
    for line, claim_id in rejected:
        problems.append(
            ClaimProblem(
                "high",
                "CLAIM_MARKER_CONTEXT",
                f"claim block marker is not attached to a renderable unclaimed block: {claim_id}",
                f"body:{line}",
            )
        )
        if not CLAIM_ID_RE.fullmatch(claim_id):
            problems.append(
                ClaimProblem(
                    "high",
                    "CLAIM_ID_INVALID",
                    f"claim block ID contains unsupported characters: {claim_id}",
                    f"body:{line}",
                )
            )
    for claim_id in supported:
        if not CLAIM_ID_RE.fullmatch(claim_id):
            problems.append(
                ClaimProblem(
                    "high",
                    "EVIDENCE_CLAIM_ID_INVALID",
                    f"evidence supports an invalid claim ID: {claim_id}",
                    "evidence",
                )
            )
    for claim_id, records in by_id.items():
        if len(records) > 1:
            problems.append(
                ClaimProblem(
                    "high",
                    "CLAIM_ANCHOR_DUPLICATE",
                    f"claim block ID is defined more than once: {claim_id}",
                    "body",
                )
            )
    heading_ids = rendered_heading_fragments(body, scalar_text(data.get("title")))
    reserved_fragments = heading_ids | FIXED_PAGE_FRAGMENT_IDS
    for claim_id in by_id:
        if claim_id in reserved_fragments:
            problems.append(
                ClaimProblem(
                    "high",
                    "CLAIM_FRAGMENT_COLLISION",
                    f"claim block ID collides with another page fragment: {claim_id}",
                    "body",
                )
            )
    if require_anchors:
        for claim_id in supported:
            if claim_id not in by_id:
                problems.append(
                    ClaimProblem(
                        "high",
                        "EVIDENCE_CLAIM_UNRESOLVED",
                        f"evidence supports a claim with no body block anchor: {claim_id}",
                        "evidence",
                    )
                )
        supported_set = set(supported)
        for claim_id in by_id:
            if CLAIM_ID_RE.fullmatch(claim_id) and claim_id not in supported_set:
                problems.append(
                    ClaimProblem(
                        "medium",
                        "CLAIM_ANCHOR_UNREFERENCED",
                        f"claim block anchor has no supporting evidence: {claim_id}",
                        "body",
                    )
                )
    return tuple(problems)
