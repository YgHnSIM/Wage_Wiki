# SCHEMAS KNOWLEDGE BASE

## OVERVIEW

This directory defines machine-checkable entity shape, vocabulary, versioning, and canonical ID compatibility.

## WHERE TO LOOK

- `frontmatter-v1.4.schema.json`: required metadata and entity structure.
- `vocabularies-v1.4.json`: controlled values and enum semantics.
- `id-aliases.json`: historical identifiers mapped to canonical IDs.
- Other JSON files: contract-specific or migration support definitions.

## CONVENTIONS

- Treat schema and vocabulary changes as compatibility-sensitive.
- Keep identifiers stable; add aliases rather than renaming canonical IDs.
- Update contract tests and validation reports when a schema boundary changes.
- Schema version fields must agree with the corresponding entity metadata and migration rules.

## ANTI-PATTERNS

- Do not loosen required fields merely to accommodate malformed corpus data.
- Do not introduce free-form enum values when a vocabulary exists.
- Do not delete old aliases without checking all tracked references.
