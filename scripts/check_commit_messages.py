#!/usr/bin/env python3
"""Validate Git commit messages against the Wage Wiki commit protocol."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


SUBJECT_RE = re.compile(
    r"^(?P<type>[a-z]+)\((?P<scope>[a-z0-9-]+)\): (?P<summary>.+)$"
)
KOREAN_RE = re.compile(r"[가-힣]")


@dataclass(frozen=True)
class CommitRecord:
    commit: str
    message: str
    changed_files: tuple[str, ...] = ()
    is_merge: bool = False


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout


def load_policy(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != "1.0":
        raise ValueError("unsupported commit-message policy schema_version")
    if not isinstance(data.get("types"), dict) or not data["types"]:
        raise ValueError("commit-message policy requires non-empty types")
    if not isinstance(data.get("scope_groups"), dict):
        raise ValueError("commit-message policy requires scope_groups")
    return data


def allowed_scopes(policy: dict[str, Any], type_name: str) -> set[str]:
    type_policy = policy.get("types", {}).get(type_name, {})
    scopes = set(type_policy.get("allowed_scopes", []))
    groups = policy.get("scope_groups", {})
    for group_name in type_policy.get("allowed_scope_groups", []):
        scopes.update(groups.get(group_name, []))
    return scopes


def _body_sections(body: str) -> set[str]:
    sections: set[str] = set()
    for line in body.splitlines():
        match = re.match(r"^([A-Za-z][A-Za-z0-9_-]*):(?:\s.*)?$", line.strip())
        if match:
            sections.add(match.group(1))
    return sections


def _body_required(
    policy: dict[str, Any], type_name: str, changed_files: Iterable[str]
) -> tuple[bool, list[str]]:
    body_policy = policy.get("body", {})
    files = tuple(changed_files)
    reasons: list[str] = []
    if type_name in body_policy.get("required_types", []):
        reasons.append(f"type={type_name}")
    threshold = body_policy.get("required_when_files_changed_at_least")
    if isinstance(threshold, int) and threshold > 0 and len(files) >= threshold:
        reasons.append(f"files={len(files)}")
    prefixes = tuple(body_policy.get("required_path_prefixes", []))
    matching_prefixes = sorted(
        {prefix for prefix in prefixes if any(path.startswith(prefix) for path in files)}
    )
    reasons.extend(f"path={prefix}" for prefix in matching_prefixes)
    return bool(reasons), reasons


def validate_record(record: CommitRecord, policy: dict[str, Any]) -> list[dict[str, str]]:
    if record.is_merge and policy.get("allow_merge_commits", False):
        return []

    lines = record.message.rstrip("\n").splitlines()
    subject = lines[0].strip() if lines else ""
    body = "\n".join(lines[1:]).strip()
    issues: list[dict[str, str]] = []

    def add(code: str, message: str) -> None:
        issues.append({"code": code, "message": message})

    match = SUBJECT_RE.fullmatch(subject)
    if not match:
        add(
            "COMMIT_SUBJECT_FORMAT",
            f"subject must match {policy.get('format', '<type>(<scope>): <summary>')}",
        )
        return issues

    type_name = match.group("type")
    scope = match.group("scope")
    summary = match.group("summary")
    types = policy.get("types", {})
    if type_name not in types:
        add("COMMIT_TYPE_UNKNOWN", f"unknown type: {type_name}")
    else:
        scopes = allowed_scopes(policy, type_name)
        if scope not in scopes:
            add(
                "COMMIT_TYPE_SCOPE_MISMATCH",
                f"scope {scope!r} is not allowed for type {type_name!r}; "
                f"allowed: {', '.join(sorted(scopes))}",
            )

    all_scopes = {
        value
        for values in policy.get("scope_groups", {}).values()
        for value in values
    }
    if scope not in all_scopes:
        add("COMMIT_SCOPE_UNKNOWN", f"unknown scope: {scope}")

    max_length = policy.get("max_subject_length", 72)
    if isinstance(max_length, int) and len(subject) > max_length:
        add(
            "COMMIT_SUBJECT_TOO_LONG",
            f"subject length {len(subject)} exceeds {max_length}",
        )
    if policy.get("require_korean_summary", False) and not KOREAN_RE.search(summary):
        add("COMMIT_SUMMARY_KOREAN", "summary must contain Korean text")
    if any(
        summary.endswith(character)
        for character in policy.get("forbidden_terminal_characters", [])
    ):
        add("COMMIT_SUMMARY_TERMINAL", "summary has forbidden terminal punctuation")
    for term in policy.get("forbidden_summary_terms", []):
        if term and term in summary:
            add("COMMIT_SUMMARY_GENERIC", f"summary contains generic term: {term}")

    required, reasons = _body_required(policy, type_name, record.changed_files)
    if required:
        if not body:
            add(
                "COMMIT_BODY_REQUIRED",
                f"body is required ({', '.join(reasons)})",
            )
        else:
            present = _body_sections(body)
            missing = [
                section
                for section in policy.get("body", {}).get("required_sections", [])
                if section not in present
            ]
            if missing:
                add(
                    "COMMIT_BODY_SECTIONS",
                    f"body is missing sections: {', '.join(missing)}",
                )
    return issues


def _commit_record(root: Path, commit: str) -> CommitRecord:
    message = _git(root, "show", "-s", "--format=%B", commit)
    files = tuple(
        line.strip()
        for line in _git(
            root,
            "-c",
            "core.quotePath=false",
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-only",
            "-r",
            "-z",
            commit,
        ).split("\0")
        if line.strip()
    )
    parents = _git(root, "rev-list", "--parents", "-n", "1", commit).split()
    return CommitRecord(
        commit=commit,
        message=message,
        changed_files=files,
        is_merge=len(parents) > 2,
    )


def _commits_for_args(root: Path, args: argparse.Namespace, policy: dict[str, Any]) -> list[str]:
    if args.commit:
        return args.commit
    if args.commit_range:
        return _git(root, "rev-list", "--reverse", args.commit_range).split()
    if args.all:
        return _git(root, "rev-list", "--reverse", "HEAD").split()
    if policy.get("history_mode") != "all":
        raise ValueError("unsupported commit-message history_mode")
    return _git(root, "rev-list", "--reverse", "HEAD").split()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--config", type=Path, default=Path("schemas/commit-message-v1.json")
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--commit", action="append", help="commit to validate")
    selection.add_argument("--range", dest="commit_range", help="Git revision range")
    selection.add_argument("--all", action="store_true", help="audit all commits")
    selection.add_argument("--message-file", type=Path, help="validate a message file")
    parser.add_argument(
        "--audit",
        action="store_true",
        help="report issues without returning a failing exit code",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    root = args.root.resolve()
    config = args.config if args.config.is_absolute() else root / args.config
    try:
        policy = load_policy(config)
        if args.message_file:
            message_path = (
                args.message_file
                if args.message_file.is_absolute()
                else root / args.message_file
            )
            records = [
                CommitRecord(commit="MESSAGE_FILE", message=message_path.read_text(encoding="utf-8"))
            ]
            selection_name = "message-file"
        else:
            commits = _commits_for_args(root, args, policy)
            records = [_commit_record(root, commit) for commit in commits]
            selection_name = (
                "all"
                if args.all
                else args.commit_range
                or ("commits" if args.commit else "policy-history")
            )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    results: list[dict[str, Any]] = []
    issue_count = 0
    for record in records:
        issues = validate_record(record, policy)
        issue_count += len(issues)
        results.append(
            {
                "commit": record.commit,
                "subject": record.message.splitlines()[0] if record.message.splitlines() else "",
                "changed_files": len(record.changed_files),
                "merge_commit": record.is_merge,
                "issues": issues,
            }
        )

    report = {
        "schema_version": "1.0",
        "selection": selection_name,
        "history_mode": policy.get("history_mode", ""),
        "audit": args.audit,
        "ok": issue_count == 0,
        "summary": {
            "commits": len(records),
            "commits_with_issues": sum(bool(result["issues"]) for result in results),
            "issues": issue_count,
        },
        "results": results,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        output = args.output if args.output.is_absolute() else root / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if args.audit or report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
