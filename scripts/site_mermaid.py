#!/usr/bin/env python3
"""Parse and render the repository's safe Mermaid flowchart subset."""

from __future__ import annotations

import hashlib
import html
import re
from typing import Any


MERMAID_DIRECTION_RE = re.compile(r"^(?:flowchart|graph)\s+(LR|RL|TD|TB|BT)\s*$", re.I)
MERMAID_NODE_ID_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*)(.*)$")
MERMAID_LABELLED_EDGE_RE = re.compile(r'^(.+?)\s+--\s*"([^"]+)"\s*-->\s*(.+?)\s*;?\s*$')
MERMAID_EDGE_RE = re.compile(r"^(.+?)\s*-->\s*(.+?)\s*;?\s*$")


def _parse_mermaid_node(token: str) -> tuple[str, str, str, bool]:
    """Parse the small, explicit Mermaid node subset used by wiki flowcharts."""

    match = MERMAID_NODE_ID_RE.fullmatch(token.strip())
    if not match:
        raise RuntimeError(f"unsupported Mermaid node: {token.strip()}")
    node_id, suffix = match.groups()
    if not suffix:
        return node_id, node_id, "rect", False

    delimiters = {"[": ("]", "rect"), "{": ("}", "decision"), "(": (")", "round")}
    closing, shape = delimiters.get(suffix[0], ("", ""))
    if not closing or not suffix.endswith(closing):
        raise RuntimeError(f"unsupported Mermaid node shape: {token.strip()}")
    label = suffix[1:-1].strip()
    if len(label) >= 2 and label[0] == label[-1] == '"':
        label = label[1:-1]
    label = re.sub(r"<br\s*/?>", "\n", label, flags=re.I).replace(r"\n", "\n").strip()
    if not label:
        label = node_id
    return node_id, label, shape, True


def _flowchart_text_lines(value: str, limit: int = 12) -> list[str]:
    """Wrap Korean and Latin labels without relying on browser-side layout."""

    result: list[str] = []
    for paragraph in value.splitlines() or [value]:
        words = paragraph.split()
        if not words:
            result.append("")
            continue
        current = ""
        for word in words:
            chunks = [word[index : index + limit] for index in range(0, len(word), limit)] or [word]
            for chunk in chunks:
                candidate = f"{current} {chunk}".strip()
                if current and len(candidate) > limit:
                    result.append(current)
                    current = chunk
                else:
                    current = candidate
        if current:
            result.append(current)
    return result or [value]


def _parse_mermaid_flowchart(source: str) -> tuple[str, dict[str, dict[str, Any]], list[dict[str, str]], list[str]]:
    lines = [line.strip() for line in source.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    lines = [line for line in lines if line and not line.startswith("%%")]
    if not lines:
        raise RuntimeError("empty Mermaid flowchart")
    direction_match = MERMAID_DIRECTION_RE.fullmatch(lines[0])
    if not direction_match:
        raise RuntimeError("only Mermaid flowchart LR/RL/TD/TB/BT diagrams are supported")

    direction = direction_match.group(1).upper()
    nodes: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    edges: list[dict[str, str]] = []

    def register(token: str) -> str:
        node_id, label, shape, explicit = _parse_mermaid_node(token)
        if node_id not in nodes:
            nodes[node_id] = {"id": node_id, "label": label, "shape": shape, "explicit": explicit}
            order.append(node_id)
        elif explicit:
            nodes[node_id].update({"label": label, "shape": shape, "explicit": True})
        return node_id

    for line in lines[1:]:
        labelled_match = MERMAID_LABELLED_EDGE_RE.fullmatch(line)
        if labelled_match:
            left, label, right = labelled_match.groups()
        else:
            edge_match = MERMAID_EDGE_RE.fullmatch(line)
            if edge_match:
                left, right = edge_match.groups()
                label = ""
            else:
                register(line.rstrip(";"))
                continue
        source_id = register(left)
        target_id = register(right)
        if source_id == target_id:
            raise RuntimeError("self-referencing Mermaid flowchart edges are not supported")
        edges.append({"source": source_id, "target": target_id, "label": label.strip()})

    if len(nodes) < 2 or not edges:
        raise RuntimeError("Mermaid flowchart must contain at least two connected nodes")
    return direction, nodes, edges, order


def _flowchart_ranks(
    nodes: dict[str, dict[str, Any]], edges: list[dict[str, str]], order: list[str]
) -> dict[str, int]:
    order_index = {node_id: index for index, node_id in enumerate(order)}
    indegree = {node_id: 0 for node_id in nodes}
    outgoing: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    for edge in edges:
        indegree[edge["target"]] += 1
        outgoing[edge["source"]].append(edge["target"])

    queue = [node_id for node_id in order if indegree[node_id] == 0]
    ranks = {node_id: 0 for node_id in nodes}
    visited: list[str] = []
    while queue:
        node_id = queue.pop(0)
        visited.append(node_id)
        for target_id in outgoing[node_id]:
            ranks[target_id] = max(ranks[target_id], ranks[node_id] + 1)
            indegree[target_id] -= 1
            if indegree[target_id] == 0:
                queue.append(target_id)
                queue.sort(key=order_index.get)
    if len(visited) != len(nodes):
        raise RuntimeError("cyclic Mermaid flowcharts are not supported by the static renderer")
    return ranks


def render_mermaid_flowchart(source: str, chart_seed: str) -> str:
    """Render a dependency-free, responsive SVG from a safe Mermaid flowchart subset."""

    source_direction, nodes, edges, order = _parse_mermaid_flowchart(source)
    ranks = _flowchart_ranks(nodes, edges, order)
    digest = hashlib.sha256(f"{chart_seed}\n{source}".encode("utf-8")).hexdigest()[:12]
    marker_id = f"flow-arrow-{digest}"
    title_id = f"flow-title-{digest}"
    desc_id = f"flow-desc-{digest}"

    for node in nodes.values():
        line_limit = 8
        node["lines"] = _flowchart_text_lines(node["label"], line_limit)
        longest = max(len(line) for line in node["lines"])
        base_width = min(156.0, max(124.0, longest * 14.5 + 24.0))
        node["width"] = 200.0 if node["shape"] == "decision" else base_width
        text_height = 20.0 * len(node["lines"])
        node["height"] = max(120.0, text_height + 60.0) if node["shape"] == "decision" else max(58.0, text_height + 24.0)

    groups: dict[int, list[str]] = {}
    for node_id in order:
        groups.setdefault(ranks[node_id], []).append(node_id)
    ordered_ranks = sorted(groups)
    margin = 20.0
    horizontal_gap = 28.0
    vertical_gap = 72.0
    row_widths = {
        rank: sum(float(nodes[node_id]["width"]) for node_id in groups[rank])
        + horizontal_gap * max(0, len(groups[rank]) - 1)
        for rank in ordered_ranks
    }
    row_heights = {rank: max(float(nodes[node_id]["height"]) for node_id in groups[rank]) for rank in ordered_ranks}
    canvas_width = max(row_widths.values()) + margin * 2
    canvas_height = sum(row_heights.values()) + vertical_gap * max(0, len(ordered_ranks) - 1) + margin * 2

    y_cursor = margin
    for rank in ordered_ranks:
        row_height = row_heights[rank]
        x_cursor = (canvas_width - row_widths[rank]) / 2
        for node_id in groups[rank]:
            node = nodes[node_id]
            width = float(node["width"])
            node["x"] = x_cursor + width / 2
            node["y"] = y_cursor + row_height / 2
            x_cursor += width + horizontal_gap
        y_cursor += row_height + vertical_gap

    edge_markup: list[str] = []
    for edge in edges:
        source_node = nodes[edge["source"]]
        target_node = nodes[edge["target"]]
        x1 = float(source_node["x"])
        y1 = float(source_node["y"]) + float(source_node["height"]) / 2
        x2 = float(target_node["x"])
        y2 = float(target_node["y"]) - float(target_node["height"]) / 2
        rank_distance = ranks[edge["target"]] - ranks[edge["source"]]
        if rank_distance > 1:
            lane_x = 8.0 if x1 <= canvas_width / 2 else canvas_width - 8.0
            path = (
                f"M {x1:.1f} {y1:.1f} C {x1:.1f} {y1 + 18:.1f}, {lane_x:.1f} {y1 + 18:.1f}, "
                f"{lane_x:.1f} {y1 + 38:.1f} L {lane_x:.1f} {y2 - 38:.1f} "
                f"C {lane_x:.1f} {y2 - 18:.1f}, {x2:.1f} {y2 - 18:.1f}, {x2:.1f} {y2:.1f}"
            )
            label_x = lane_x
            label_y = (y1 + y2) / 2
        else:
            delta = max(20.0, (y2 - y1) * 0.45)
            path = f"M {x1:.1f} {y1:.1f} C {x1:.1f} {y1 + delta:.1f}, {x2:.1f} {y2 - delta:.1f}, {x2:.1f} {y2:.1f}"
            label_x = (x1 + x2) / 2
            label_y = (y1 + y2) / 2
        edge_markup.append(
            f'<path d="{path}" marker-end="url(#{marker_id})"></path>'
        )
        if edge["label"]:
            label_width = max(34.0, len(edge["label"]) * 12.0 + 14.0)
            label_x = min(max(label_x, label_width / 2 + 2.0), canvas_width - label_width / 2 - 2.0)
            edge_markup.append(
                f'<g class="flowchart__edge-label" transform="translate({label_x:.1f} {label_y:.1f})">'
                f'<rect x="{-label_width / 2:.1f}" y="-12" width="{label_width:.1f}" height="24"></rect>'
                f'<text text-anchor="middle" dominant-baseline="central">{html.escape(edge["label"])}</text></g>'
            )

    node_markup: list[str] = []
    for node_id in order:
        node = nodes[node_id]
        x = float(node["x"])
        y = float(node["y"])
        width = float(node["width"])
        height = float(node["height"])
        classes = f'flowchart__node flowchart__node--{node["shape"]}'
        if node["shape"] == "decision":
            shape_markup = (
                f'<polygon points="{x:.1f},{y - height / 2:.1f} {x + width / 2:.1f},{y:.1f} '
                f'{x:.1f},{y + height / 2:.1f} {x - width / 2:.1f},{y:.1f}"></polygon>'
            )
        else:
            radius = min(24.0, height / 2) if node["shape"] == "round" else 0.0
            shape_markup = (
                f'<rect x="{x - width / 2:.1f}" y="{y - height / 2:.1f}" width="{width:.1f}" '
                f'height="{height:.1f}" rx="{radius:.1f}"></rect>'
            )
        text_y = y - (len(node["lines"]) - 1) * 10.0
        tspans = "".join(
            f'<tspan x="{x:.1f}" y="{text_y + line_index * 20.0:.1f}">{html.escape(line)}</tspan>'
            for line_index, line in enumerate(node["lines"])
        )
        node_markup.append(f'<g class="{classes}">{shape_markup}<text text-anchor="middle">{tspans}</text></g>')

    descriptions = []
    for edge in edges:
        relation = f"{nodes[edge['source']]['label']}에서 {nodes[edge['target']]['label']}로 이동"
        if edge["label"]:
            relation += f"({edge['label']})"
        descriptions.append(relation)
    description = ". ".join(descriptions) + "."
    orientation_class = "horizontal-source" if source_direction in {"LR", "RL"} else "vertical-source"
    return (
        f'<figure class="flowchart flowchart--{orientation_class}" data-source-direction="{source_direction}">'
        f'<svg class="flowchart__svg" viewBox="0 0 {canvas_width:.1f} {canvas_height:.1f}" '
        f'role="img" aria-labelledby="{title_id} {desc_id}">'
        f'<title id="{title_id}">절차 흐름도</title><desc id="{desc_id}">{html.escape(description)}</desc>'
        f'<defs><marker id="{marker_id}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
        f'<path class="flowchart__arrow" d="M 0 0 L 10 5 L 0 10 z"></path></marker></defs>'
        f'<g class="flowchart__edges">{"".join(edge_markup)}</g>'
        f'<g class="flowchart__nodes">{"".join(node_markup)}</g></svg></figure>'
    )
