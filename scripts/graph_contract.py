#!/usr/bin/env python3
"""Shared field-to-entity mapping for legacy related_* graph links."""

from __future__ import annotations

from types import MappingProxyType


RELATED_FIELD_TYPES = MappingProxyType(
    {
        "related_concepts": "concept",
        "related_rules": "rule",
        "related_cases": "case",
        "related_laws": "law",
        "related_interpretations": "interpretation",
        "related_fact_patterns": "fact_pattern",
    }
)
RELATED_FIELDS = tuple(RELATED_FIELD_TYPES)
