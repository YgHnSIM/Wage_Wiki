"""Standard-library helpers for Wage Wiki maintenance tools.

The frontmatter reader intentionally implements a conservative YAML subset.  It
does not evaluate tags, constructors, anchors, or arbitrary objects.  This is
enough for the repository's mappings, lists, flow lists, and scalar values while
remaining safe on untrusted source text.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator


SCHEMA_VERSION = "1.3"
SEVERITIES = ("critical", "high", "medium", "low", "info")
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
URL_RE = re.compile(r"^https?://", re.I)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class FrontmatterError(ValueError):
    """Raised when frontmatter is malformed or uses unsupported unsafe YAML."""


@dataclass(frozen=True)
class Token:
    indent: int
    text: str
    line: int


@dataclass
class Entity:
    path: Path
    relative_path: str
    data: dict[str, Any]
    body: str


def _strip_comment(value: str) -> str:
    quote: str | None = None
    escaped = False
    depth = 0
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if quote == '"' and char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char in ("'", '"'):
            quote = char
        elif char in "[{(":
            depth += 1
        elif char in "]})":
            depth = max(0, depth - 1)
        elif char == "#" and depth == 0 and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
    return value.rstrip()


def _split_flow(value: str) -> list[str]:
    parts: list[str] = []
    start = 0
    quote: str | None = None
    escaped = False
    depth = 0
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if quote == '"' and char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char in ("'", '"'):
            quote = char
        elif char in "[{(":
            depth += 1
        elif char in "]})":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(value[start:index].strip())
            start = index + 1
    parts.append(value[start:].strip())
    return [part for part in parts if part]


def _split_key_value(text: str, line: int) -> tuple[str, str]:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if quote == '"' and char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char in ("'", '"'):
            quote = char
        elif char == ":":
            key = text[:index].strip()
            if not key:
                raise FrontmatterError(f"line {line}: empty mapping key")
            return key, text[index + 1 :].strip()
    raise FrontmatterError(f"line {line}: expected ':' in mapping")


def parse_scalar(value: str) -> Any:
    value = _strip_comment(value).strip()
    if value == "":
        return ""
    if value in ("null", "Null", "NULL", "~"):
        return None
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    if value.startswith('"') and value.endswith('"'):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise FrontmatterError(f"invalid double-quoted scalar: {exc}") from exc
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [] if not inner else [parse_scalar(part) for part in _split_flow(inner)]
    if value.startswith("{") and value.endswith("}"):
        inner = value[1:-1].strip()
        result: dict[str, Any] = {}
        if not inner:
            return result
        for part in _split_flow(inner):
            key, item = _split_key_value(part, 0)
            key_value = parse_scalar(key)
            key_text = str(key_value)
            if key_text in result:
                raise FrontmatterError(f"duplicate flow mapping key: {key_text}")
            result[key_text] = parse_scalar(item)
        return result
    if re.fullmatch(r"[-+]?\d+", value):
        try:
            return int(value)
        except ValueError:
            pass
    if re.fullmatch(r"[-+]?(?:\d+\.\d*|\.\d+)", value):
        try:
            return float(value)
        except ValueError:
            pass
    if value.startswith("!") or value.startswith("&") or value.startswith("*"):
        raise FrontmatterError("YAML tags, anchors, and aliases are not supported")
    return value


class _SubsetYamlParser:
    def __init__(self, text: str, line_offset: int = 0) -> None:
        self.tokens: list[Token] = []
        for number, raw_line in enumerate(text.splitlines(), start=1 + line_offset):
            if not raw_line.strip() or raw_line.lstrip().startswith("#"):
                continue
            leading = raw_line[: len(raw_line) - len(raw_line.lstrip(" \t"))]
            if "\t" in leading:
                raise FrontmatterError(f"line {number}: tabs are not allowed for indentation")
            self.tokens.append(Token(len(leading), raw_line[len(leading) :].rstrip(), number))
        self.position = 0

    def parse(self) -> dict[str, Any]:
        if not self.tokens:
            return {}
        if self.tokens[0].indent != 0 or self.tokens[0].text.startswith("-"):
            raise FrontmatterError(f"line {self.tokens[0].line}: frontmatter root must be a mapping")
        result = self._parse_mapping(0)
        if self.position != len(self.tokens):
            token = self.tokens[self.position]
            raise FrontmatterError(f"line {token.line}: unexpected indentation")
        return result

    def _parse_node(self, indent: int) -> Any:
        token = self.tokens[self.position]
        if token.indent != indent:
            raise FrontmatterError(f"line {token.line}: inconsistent indentation")
        return self._parse_list(indent) if token.text.startswith("-") else self._parse_mapping(indent)

    def _parse_mapping(self, indent: int) -> dict[str, Any]:
        result: dict[str, Any] = {}
        while self.position < len(self.tokens):
            token = self.tokens[self.position]
            if token.indent < indent:
                break
            if token.indent > indent:
                raise FrontmatterError(f"line {token.line}: unexpected indentation")
            if token.text.startswith("-"):
                break
            key, raw_value = _split_key_value(token.text, token.line)
            key = str(parse_scalar(key))
            if key in result:
                raise FrontmatterError(f"line {token.line}: duplicate key '{key}'")
            self.position += 1
            if raw_value in ("|", ">", "|-", ">-", "|+", ">+"):
                result[key] = self._parse_block_scalar(indent, raw_value)
            elif raw_value:
                result[key] = parse_scalar(raw_value)
            elif self.position < len(self.tokens) and self.tokens[self.position].indent > indent:
                result[key] = self._parse_node(self.tokens[self.position].indent)
            else:
                result[key] = None
        return result

    def _parse_list(self, indent: int) -> list[Any]:
        result: list[Any] = []
        while self.position < len(self.tokens):
            token = self.tokens[self.position]
            if token.indent < indent:
                break
            if token.indent != indent or not token.text.startswith("-"):
                break
            rest = token.text[1:].strip()
            self.position += 1
            if not rest:
                if self.position < len(self.tokens) and self.tokens[self.position].indent > indent:
                    result.append(self._parse_node(self.tokens[self.position].indent))
                else:
                    result.append(None)
                continue
            try:
                key, raw_value = _split_key_value(rest, token.line)
                mapping_item = True
            except FrontmatterError:
                mapping_item = False
            if not mapping_item:
                result.append(parse_scalar(rest))
                if self.position < len(self.tokens) and self.tokens[self.position].indent > indent:
                    child = self.tokens[self.position]
                    raise FrontmatterError(f"line {child.line}: scalar list item cannot have children")
                continue
            item: dict[str, Any] = {}
            key = str(parse_scalar(key))
            if raw_value:
                item[key] = parse_scalar(raw_value)
            elif self.position < len(self.tokens) and self.tokens[self.position].indent > indent:
                child_indent = self.tokens[self.position].indent
                item[key] = self._parse_node(child_indent)
            else:
                item[key] = None
            if self.position < len(self.tokens) and self.tokens[self.position].indent > indent:
                extra_indent = self.tokens[self.position].indent
                extra = self._parse_mapping(extra_indent)
                overlap = set(item) & set(extra)
                if overlap:
                    raise FrontmatterError(f"line {token.line}: duplicate list mapping key(s): {sorted(overlap)}")
                item.update(extra)
            result.append(item)
        return result

    def _parse_block_scalar(self, parent_indent: int, style: str) -> str:
        # Tokens omit blank lines; block scalars are supported for concise notes,
        # while exact whitespace-preserving source excerpts should remain quoted.
        lines: list[str] = []
        if self.position >= len(self.tokens) or self.tokens[self.position].indent <= parent_indent:
            return ""
        block_indent = self.tokens[self.position].indent
        while self.position < len(self.tokens) and self.tokens[self.position].indent >= block_indent:
            token = self.tokens[self.position]
            lines.append(" " * (token.indent - block_indent) + token.text)
            self.position += 1
        separator = "\n" if style.startswith("|") else " "
        value = separator.join(lines)
        return value if style.endswith("-") else value + "\n"


def parse_frontmatter_text(text: str) -> tuple[dict[str, Any], str]:
    text = text.lstrip("\ufeff")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise FrontmatterError("file does not start with a frontmatter delimiter")
    closing = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            closing = index
            break
    if closing is None:
        raise FrontmatterError("frontmatter closing delimiter is missing")
    frontmatter = "".join(lines[1:closing])
    body = "".join(lines[closing + 1 :])
    return _SubsetYamlParser(frontmatter, line_offset=1).parse(), body


def load_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    return parse_frontmatter_text(path.read_text(encoding="utf-8-sig"))


def iter_markdown(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*.md"), key=lambda item: item.as_posix().casefold()):
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        yield path


def load_entities(repo_root: Path) -> tuple[list[Entity], list[dict[str, Any]]]:
    wiki_root = repo_root / "wiki"
    entities: list[Entity] = []
    issues: list[dict[str, Any]] = []
    if not wiki_root.exists():
        return entities, [issue("critical", "WIKI_MISSING", "wiki", "wiki directory does not exist")]
    for path in iter_markdown(wiki_root):
        relative = path.relative_to(repo_root).as_posix()
        if "logs" in path.relative_to(wiki_root).parts or path.name == "index.md":
            continue
        try:
            data, body = load_frontmatter(path)
        except (OSError, UnicodeError, FrontmatterError) as exc:
            issues.append(issue("critical", "FRONTMATTER_PARSE", relative, str(exc)))
            continue
        if not data.get("entity_type"):
            issues.append(issue("high", "ENTITY_TYPE_MISSING", relative, "entity_type is missing"))
            continue
        entities.append(Entity(path, relative, data, body))
    return entities, issues


def issue(severity: str, code: str, path: str, message: str, field: str = "") -> dict[str, Any]:
    return {"severity": severity, "code": code, "path": path, "field": field, "message": message}


def as_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    return value if isinstance(value, list) else [value]


def scalar_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def wiki_targets(value: Any) -> list[str]:
    result: list[str] = []
    for item in as_list(value):
        if not isinstance(item, str):
            continue
        matches = WIKILINK_RE.findall(item)
        result.extend(match.strip() for match in matches)
        if not matches and item.strip() and not URL_RE.match(item.strip()):
            result.append(item.strip())
    return result


def normalized_ref(value: str) -> str:
    value = value.strip().replace("\\", "/")
    value = re.sub(r"^\./", "", value)
    value = value.lstrip("/")
    if value.lower().endswith(".md"):
        value = value[:-3]
    return value.casefold()


def entity_lookup(entities: Iterable[Entity]) -> tuple[dict[str, Entity], dict[str, list[Entity]]]:
    by_id: dict[str, Entity] = {}
    names: dict[str, list[Entity]] = defaultdict(list)
    for entity in entities:
        entity_id = scalar_text(entity.data.get("id"))
        if entity_id and entity_id not in by_id:
            by_id[entity_id] = entity
        candidates = [
            entity_id,
            scalar_text(entity.data.get("title")),
            entity.path.stem,
            entity.relative_path,
            entity.relative_path.removeprefix("wiki/"),
        ]
        candidates.extend(scalar_text(item) for item in as_list(entity.data.get("aliases")))
        candidates.extend(scalar_text(item) for item in as_list(entity.data.get("id_aliases")))
        for candidate in candidates:
            if not candidate:
                continue
            variants = {normalized_ref(candidate), normalized_ref(Path(candidate).name)}
            for variant in variants:
                if entity not in names[variant]:
                    names[variant].append(entity)
    return by_id, names


def resolve_entity_ref(target: str, names: dict[str, list[Entity]]) -> list[Entity]:
    normalized = normalized_ref(target)
    matches = names.get(normalized, [])
    if matches:
        return matches
    return names.get(normalized_ref(Path(normalized).name), [])


def parse_date(value: Any) -> dt.date | None:
    text = scalar_text(value)
    if not DATE_RE.fullmatch(text):
        return None
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default


def load_registry_ids(repo_root: Path) -> set[str]:
    path = repo_root / "sources" / "registry.yaml"
    if not path.exists():
        return set()
    try:
        data = _SubsetYamlParser(path.read_text(encoding="utf-8-sig")).parse()
    except (OSError, UnicodeError, FrontmatterError):
        return set()
    return {
        scalar_text(record.get("source_id"))
        for record in as_list(data.get("sources"))
        if isinstance(record, dict) and scalar_text(record.get("source_id"))
    }


def load_path_aliases(repo_root: Path) -> dict[str, str]:
    path = repo_root / "sources" / "path_aliases.yaml"
    if not path.exists():
        return {}
    try:
        data = _SubsetYamlParser(path.read_text(encoding="utf-8-sig")).parse()
    except (OSError, UnicodeError, FrontmatterError):
        return {}
    aliases = data.get("aliases", {})
    if not isinstance(aliases, dict):
        return {}
    return {normalized_ref(str(old)): normalized_ref(str(new)) for old, new in aliases.items()}


def report_summary(issues: Iterable[dict[str, Any]], entity_count: int) -> dict[str, Any]:
    counts = Counter(item.get("severity", "info") for item in issues)
    return {
        "entities": entity_count,
        "issues": sum(counts.values()),
        "by_severity": {severity: counts.get(severity, 0) for severity in SEVERITIES},
    }


def write_json(data: Any, output: Path | None) -> None:
    rendered = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if output is None:
        print(rendered, end="")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8", newline="\n")


def _dump_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def dump_subset_yaml(data: dict[str, Any]) -> str:
    """Serialize the repository's safe YAML subset with deterministic spacing."""

    lines: list[str] = []

    def emit_mapping(mapping: dict[str, Any], indent: int) -> None:
        prefix = " " * indent
        for key, value in mapping.items():
            if isinstance(value, dict):
                if value:
                    lines.append(f"{prefix}{key}:")
                    emit_mapping(value, indent + 2)
                else:
                    lines.append(f"{prefix}{key}: {{}}")
            elif isinstance(value, list):
                if value:
                    lines.append(f"{prefix}{key}:")
                    emit_list(value, indent + 2)
                else:
                    lines.append(f"{prefix}{key}: []")
            else:
                lines.append(f"{prefix}{key}: {_dump_scalar(value)}")

    def emit_list(values: list[Any], indent: int) -> None:
        prefix = " " * indent
        for value in values:
            if isinstance(value, dict):
                if not value:
                    lines.append(f"{prefix}- {{}}")
                    continue
                first_key = next(iter(value))
                first_value = value[first_key]
                if isinstance(first_value, (dict, list)):
                    lines.append(f"{prefix}- {first_key}:")
                    if isinstance(first_value, dict):
                        emit_mapping(first_value, indent + 4)
                    else:
                        emit_list(first_value, indent + 4)
                else:
                    lines.append(f"{prefix}- {first_key}: {_dump_scalar(first_value)}")
                remainder = {key: item for key, item in value.items() if key != first_key}
                emit_mapping(remainder, indent + 2)
            elif isinstance(value, list):
                lines.append(f"{prefix}-")
                emit_list(value, indent + 2)
            else:
                lines.append(f"{prefix}- {_dump_scalar(value)}")

    emit_mapping(data, 0)
    return "\n".join(lines) + "\n"


def severity_fails(issues: Iterable[dict[str, Any]], fail_on: str) -> bool:
    if fail_on == "none":
        return False
    threshold = SEVERITIES.index(fail_on)
    return any(SEVERITIES.index(item.get("severity", "info")) <= threshold for item in issues)
