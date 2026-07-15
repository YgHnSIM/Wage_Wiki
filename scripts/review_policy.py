#!/usr/bin/env python3
"""Shared freshness and review-cycle policy for knowledge entities."""

from __future__ import annotations

import datetime as dt
from typing import Any

from kg_common import parse_date


REVIEW_CYCLE_DAYS = {
    "monthly": 31,
    "quarterly": 92,
    "annual": 366,
}
RECENT_CASE_WINDOW_DAYS = 730


def recommended_review_cycle(
    entity_type: str,
    title: str,
    data: dict[str, Any],
    as_of: dt.date,
) -> str:
    """Return the repository policy cycle for an entity at a given date."""

    if entity_type == "discussion":
        return "monthly" if "최신 동향" in title else "quarterly"
    if entity_type in {"rule", "law", "interpretation"}:
        return "quarterly"
    if entity_type == "case":
        decision_date = parse_date(data.get("decision_date"))
        if decision_date and decision_date >= as_of - dt.timedelta(days=RECENT_CASE_WINDOW_DAYS):
            return "quarterly"
    return "annual"


def review_deadline_passed(checked: dt.date, cycle: str, today: dt.date) -> bool:
    """Return whether a completed review is older than its configured cycle."""

    days = REVIEW_CYCLE_DAYS.get(cycle)
    return days is not None and (today - checked).days > days
