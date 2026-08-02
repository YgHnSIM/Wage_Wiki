# SCRIPTS KNOWLEDGE BASE

## OVERVIEW

Python 3.10+ command-line tools implement the repository's contracts, policies, migrations, projections, and CI checks.

## WHERE TO LOOK

| Concern | Files |
|---|---|
| Shared parsing/path helpers | `kg_common.py` |
| Schema and entity contracts | `schema_contract.py`, `claim_contract.py`, `verification_contract.py`, `graph_contract.py`, `log_contract.py` |
| Legal decision policies | `authority_policy.py`, `temporal_policy.py`, `review_policy.py`, `verification_policy.py` |
| Source and ID integrity | `source_catalog.py`, `validate_source_registry.py`, `check_id_registry.py`, `check_path_aliases.py` |
| Corpus lint and QA | `lint_wiki.py`, `lint_sources.py`, `check_qa_regression.py`, `check_quality_baseline.py` |
| Outputs | `build_manifest.py`, `export_graph.py`, `build_search_index.py`, `build_dashboard.py`, `build_site.py` |
| Tests | `scripts/tests/` via `python -m unittest discover -s scripts/tests -v` |

## CONVENTIONS

- Scripts are executable from repository root and accept explicit output paths.
- Reports are JSON/JSONL and should be written under ignored `build/` unless a tracked registry is intentionally requested.
- Shared semantics belong in a contract/policy module; CLI wrappers should not duplicate validation rules.
- Migrations are dry-run by default. Mutation requires an explicit `--write` flag.

## ANTI-PATTERNS

- Do not make a checker pass by weakening a schema, policy, or baseline.
- Do not import generated files from `build/` as source of truth.
- Do not change a migration without preserving its plan/report behavior and tests.
- Do not run scripts from a different working directory unless the CLI explicitly supports it.
