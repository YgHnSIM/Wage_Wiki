#!/usr/bin/env python3
"""Load and cross-check the machine-readable v1.3 schema contract."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from kg_common import SCHEMA_VERSION


class SchemaContractError(ValueError):
    """Raised when a schema artifact cannot be loaded as a JSON object."""


@dataclass(frozen=True)
class ContractProblem:
    code: str
    message: str
    field: str = ""


@dataclass(frozen=True)
class SchemaContract:
    schema_version: str
    required_fields: frozenset[str]
    required_by_entity_type: Mapping[str, frozenset[str]]
    string_list_fields: frozenset[str]
    controlled_fields: Mapping[str, frozenset[str]]
    relation_types: frozenset[str]
    vocabulary: Mapping[str, Any]
    problems: tuple[ContractProblem, ...]


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SchemaContractError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SchemaContractError(f"{path} must contain a JSON object")
    return value


def _string_list_fields(properties: Mapping[str, Any]) -> frozenset[str]:
    fields: set[str] = set()
    for field, definition in properties.items():
        if not isinstance(definition, dict):
            continue
        if scalar_ref := definition.get("$ref"):
            if str(scalar_ref).endswith("/$defs/stringArray"):
                fields.add(field)
            continue
        if definition.get("type") != "array":
            continue
        items = definition.get("items")
        if isinstance(items, dict) and (items.get("type") == "string" or "enum" in items):
            fields.add(field)
    return frozenset(fields)


def _required_by_type(schema: Mapping[str, Any]) -> Mapping[str, frozenset[str]]:
    result: dict[str, frozenset[str]] = {}
    for rule in schema.get("allOf", []):
        if not isinstance(rule, dict):
            continue
        condition = rule.get("if", {})
        then = rule.get("then", {})
        try:
            entity_type = condition["properties"]["entity_type"]["const"]
        except (KeyError, TypeError):
            continue
        required = then.get("required", []) if isinstance(then, dict) else []
        if isinstance(entity_type, str) and isinstance(required, list):
            result[entity_type] = frozenset(str(field) for field in required)
    return MappingProxyType(result)


def _schema_controlled_values(
    field: str,
    properties: Mapping[str, Any],
    definitions: Mapping[str, Any],
) -> frozenset[str] | None:
    definition = properties.get(field)
    if field == "relation_type":
        try:
            definition = definitions["relation"]["properties"]["relation_type"]
        except (KeyError, TypeError):
            return None
    if not isinstance(definition, dict):
        return None
    values = definition.get("enum")
    if not isinstance(values, list):
        const = definition.get("const")
        if const is not None:
            values = [const]
        else:
            items = definition.get("items")
            values = items.get("enum") if isinstance(items, dict) else None
    if not isinstance(values, list):
        return None
    return frozenset(str(value) for value in values)


def load_schema_contract(root: Path) -> SchemaContract:
    """Load schema/vocabulary artifacts and report any contract drift."""

    schema = _read_json_object(root / "schemas" / "frontmatter-v1.3.schema.json")
    vocabulary = _read_json_object(root / "schemas" / "vocabularies.json")
    properties = schema.get("properties")
    definitions = schema.get("$defs")
    if not isinstance(properties, dict) or not isinstance(definitions, dict):
        raise SchemaContractError("frontmatter schema requires object properties and $defs")

    schema_version = str(properties.get("schema_version", {}).get("const", ""))
    required = schema.get("required", [])
    if not isinstance(required, list):
        raise SchemaContractError("frontmatter schema required must be an array")
    required_fields = frozenset(str(field) for field in required)
    required_by_type = _required_by_type(schema)

    ignored_vocabularies = {"legacy_status_aliases", "historical_only_wage_criteria"}
    controlled = {
        field: frozenset(str(value) for value in values)
        for field, values in vocabulary.items()
        if isinstance(values, list) and field not in ignored_vocabularies
    }

    problems: list[ContractProblem] = []
    vocab_version = str(vocabulary.get("schema_version", ""))
    for source, version in (("Python", SCHEMA_VERSION), ("vocabulary", vocab_version)):
        if version != schema_version:
            problems.append(
                ContractProblem(
                    "SCHEMA_VERSION_DRIFT",
                    f"{source} schema version {version or '<missing>'} differs from JSON Schema {schema_version or '<missing>'}",
                    "schema_version",
                )
            )

    for field in sorted(required_fields):
        if field not in properties:
            problems.append(
                ContractProblem(
                    "SCHEMA_REQUIRED_UNKNOWN",
                    f"required field is not declared in properties: {field}",
                    field,
                )
            )
    for entity_type, fields in required_by_type.items():
        for field in sorted(fields):
            if field not in properties:
                problems.append(
                    ContractProblem(
                        "SCHEMA_TYPE_REQUIRED_UNKNOWN",
                        f"{entity_type} requires an undeclared field: {field}",
                        field,
                    )
                )

    for field, vocab_values in controlled.items():
        schema_values = _schema_controlled_values(field, properties, definitions)
        if schema_values is None:
            problems.append(
                ContractProblem(
                    "SCHEMA_VOCAB_UNDECLARED",
                    f"controlled vocabulary has no matching schema enum: {field}",
                    field,
                )
            )
        elif schema_values != vocab_values:
            problems.append(
                ContractProblem(
                    "SCHEMA_VOCAB_DRIFT",
                    f"schema and vocabulary values differ for {field}",
                    field,
                )
            )

    return SchemaContract(
        schema_version=schema_version,
        required_fields=required_fields,
        required_by_entity_type=required_by_type,
        string_list_fields=_string_list_fields(properties),
        controlled_fields=MappingProxyType(controlled),
        relation_types=controlled.get("relation_type", frozenset()),
        vocabulary=MappingProxyType(vocabulary),
        problems=tuple(problems),
    )
