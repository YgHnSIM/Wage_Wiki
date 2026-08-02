# PROJECT KNOWLEDGE BASE

**Generated:** 2026-08-02  **Branch:** main  **Commit:** e1cc4a7

## OVERVIEW

Wage_Wiki is an Obsidian-friendly, rule-oriented legal knowledge graph for Korean labor and wage materials. Source documents remain in `raw/`; normalized entities, schemas, validation tools, and a static site are built from that corpus.

## STRUCTURE

```text
raw/        immutable source corpus, grouped by authority/material type
wiki/       normalized Guide, Rule, Case, Law, Interpretation, and related entities
schemas/    JSON Schema, vocabularies, ID aliases, contract definitions
templates/  authoring templates for v1.4 frontmatter and entity types
sources/    source registry and raw manifest
scripts/    validation, policy, migration, graph/search/site build tools
tests/      QA regression catalogue
web/        static-site CSS, JavaScript, and favicon assets
build/      ignored generated reports and site output
```

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| Add or classify source material | `raw/` | Preserve original content; route to a typed subdirectory. |
| Author legal knowledge entities | `wiki/`, `templates/` | Use canonical IDs and evidence/provenance fields. |
| Change validation semantics | `schemas/`, `scripts/*_contract.py`, `scripts/*_policy.py` | Update the contract and its checks together. |
| Build or inspect the site | `scripts/build_site.py`, `scripts/check_site.py`, `web/` | Output belongs under ignored `build/`. |
| Add regression coverage | `scripts/tests/`, `tests/qa_regression.jsonl` | Keep catalogue IDs and required authority/rule IDs valid. |

## CODE MAP

Central modules are intentionally small Python scripts rather than an application package:

| Symbol/file | Role |
|---|---|
| `scripts/kg_common.py` | Shared path, frontmatter, and entity utilities. |
| `scripts/schema_contract.py` | v1.4 schema and enum contract checks. |
| `scripts/source_catalog.py` | Source registry and raw-path resolution. |
| `scripts/claim_contract.py` / `verification_contract.py` | Claim anchors and verification metadata contracts. |
| `scripts/build_site.py` | Converts wiki entities into the static GitHub Pages site. |
| `scripts/export_graph.py` / `build_search_index.py` | Graph JSON and SQLite FTS projections. |

## CONVENTIONS

- `raw/` is append-oriented and treated as immutable evidence; derived corrections belong in `wiki/` or logs.
- Entity IDs are canonical and namespace-sensitive (`claim:`, `evidence:`, `source:`); aliases belong in `schemas/id-aliases.json`.
- Validation scripts expose deterministic CLI reports through `--output`; migrations default to dry-run and require `--write` to mutate.
- Legal status (`current`, `historical`, `superseded`, `overruled`, `future`, `unknown`) is distinct from collection status (`draft`, `review`, `verified`).

## ANTI-PATTERNS (THIS PROJECT)

- Do not edit, delete, summarize-over, or silently deduplicate original files under `raw/`.
- Do not hand-edit generated `build/`, `output/`, or `derived/` artifacts.
- Do not change canonical IDs to repair naming; add an alias and update registries.
- Do not publish a legal conclusion without linked authority, evidence locator, and verification state.
- Do not use migration `--write` without reviewing the generated plan/report first.

## COMMANDS

```text
python -m unittest discover -s scripts/tests -v
python scripts/validate_frontmatter.py --version 1.4 --output build/frontmatter-report.json --fail-on high
python scripts/lint_wiki.py --output build/lint-report.json --strict-v14 --fail-on high
python scripts/build_site.py --output build/site --site-url "http://localhost:8000/"
python scripts/check_site.py build/site --output build/site-check.json
```

## NOTES

GitHub Pages builds on pushes to `main` and runs Python 3.12, Node 24, unit tests, schema/source/wiki checks, then site generation. Existing project-specific operating rules remain in `AGENT.md`; this file is the structural knowledge map.
