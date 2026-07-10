#!/usr/bin/env python3
"""Check generated Wage Wiki HTML for broken or unsafe local references."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


EXTERNAL_SCHEMES = {"http", "https", "mailto", "tel", "data"}
LOCAL_PATH_LEAK_RE = re.compile(r"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/]|file://)", re.I)


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[tuple[str, str]] = []
        self.ids: list[str] = []
        self.h1_count = 0
        self.lang = ""
        self.images_without_alt = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "html":
            self.lang = values.get("lang", "")
        if tag == "h1":
            self.h1_count += 1
        if values.get("id"):
            self.ids.append(values["id"])
        if tag in {"a", "link"} and values.get("href"):
            self.references.append(("href", values["href"]))
        if tag in {"script", "img", "source"} and values.get("src"):
            self.references.append(("src", values["src"]))
        if values.get("data-index-url"):
            self.references.append(("data-index-url", values["data-index-url"]))
        if tag == "meta" and values.get("http-equiv", "").casefold() == "refresh":
            match = re.search(r"(?:^|;)\s*url\s*=\s*(.+)\s*$", values.get("content", ""), re.I)
            if match:
                self.references.append(("refresh", match.group(1).strip(" \"'")))
        if tag == "img" and "alt" not in values:
            self.images_without_alt += 1


def _issue(code: str, path: Path, message: str) -> dict[str, str]:
    return {"code": code, "path": path.as_posix(), "message": message}


def check_site(site_root: Path) -> dict[str, object]:
    site_root = site_root.resolve()
    issues: list[dict[str, str]] = []
    html_files = sorted(site_root.rglob("*.html"))
    if not html_files:
        issues.append(_issue("HTML_MISSING", site_root, "no HTML files found"))
    parser_by_path: dict[Path, PageParser] = {}

    for path in html_files:
        relative = path.relative_to(site_root)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            issues.append(_issue("HTML_READ", relative, str(exc)))
            continue
        if LOCAL_PATH_LEAK_RE.search(text):
            issues.append(_issue("LOCAL_PATH_LEAK", relative, "page contains a local filesystem path"))
        parser = PageParser()
        try:
            parser.feed(text)
            parser.close()
        except Exception as exc:  # HTMLParser reports malformed edge cases inconsistently.
            issues.append(_issue("HTML_PARSE", relative, str(exc)))
            continue
        parser_by_path[path] = parser
        if parser.lang != "ko":
            issues.append(_issue("LANG_MISSING", relative, "html lang must be 'ko'"))
        if len(parser.ids) != len(set(parser.ids)):
            duplicates = [item for item, count in Counter(parser.ids).items() if count > 1]
            issues.append(_issue("DUPLICATE_ID", relative, f"duplicate id(s): {duplicates}"))
        if parser.images_without_alt:
            issues.append(_issue("IMAGE_ALT", relative, f"{parser.images_without_alt} image(s) lack alt text"))
        if "aliases" not in relative.parts and parser.h1_count != 1:
            issues.append(_issue("H1_COUNT", relative, f"expected one h1, found {parser.h1_count}"))

    for page, parser in parser_by_path.items():
        relative = page.relative_to(site_root)
        for attribute, reference in parser.references:
            parsed = urlsplit(reference)
            if parsed.scheme.casefold() in EXTERNAL_SCHEMES or reference.startswith("//"):
                continue
            if parsed.scheme:
                issues.append(_issue("REFERENCE_SCHEME", relative, f"unsupported {attribute}: {reference}"))
                continue
            if parsed.path.startswith("/"):
                issues.append(_issue("ROOT_ABSOLUTE_REFERENCE", relative, f"project Pages unsafe {attribute}: {reference}"))
                continue
            target_path = unquote(parsed.path)
            target = page if not target_path else (page.parent / target_path)
            if target_path.endswith("/") or target.is_dir():
                target = target / "index.html"
            try:
                resolved = target.resolve()
                resolved.relative_to(site_root)
            except (OSError, ValueError):
                issues.append(_issue("REFERENCE_ESCAPE", relative, f"reference leaves site root: {reference}"))
                continue
            if target_path and not resolved.exists():
                issues.append(_issue("BROKEN_REFERENCE", relative, f"missing target: {reference}"))
                continue
            if parsed.fragment and resolved.suffix.casefold() == ".html" and resolved in parser_by_path:
                if unquote(parsed.fragment) not in parser_by_path[resolved].ids:
                    issues.append(_issue("BROKEN_FRAGMENT", relative, f"missing fragment: {reference}"))

    raw_files = [path for path in site_root.rglob("*") if path.is_file() and "raw" in path.relative_to(site_root).parts]
    if raw_files:
        issues.append(_issue("RAW_PUBLISHED", site_root, f"raw source files published: {len(raw_files)}"))
    return {
        "site": site_root.name,
        "html_files": len(html_files),
        "issues": len(issues),
        "by_code": dict(sorted(Counter(item["code"] for item in issues).items())),
        "details": issues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", type=Path, nargs="?", default=Path("build/site"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = check_site(args.site)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 1 if report["issues"] else 0


if __name__ == "__main__":
    sys.exit(main())
