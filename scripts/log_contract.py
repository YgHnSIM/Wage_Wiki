#!/usr/bin/env python3
"""Controlled vocabulary for append-only repository audit logs."""

from __future__ import annotations


LOG_ACTIONS = frozenset(
    {
        "CREATE",
        "UPDATE",
        "LINK",
        "DEPRECATE",
        "CONFLICT_REGISTER",
        "CONFLICT_RESOLVE",
        "LINT_RUN",
        "VERIFY",
        "INGEST",
        "MIGRATE",
        "ROUTE_RAW",
        "DEDUPE_RAW",
    }
)
