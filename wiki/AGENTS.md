# WIKI KNOWLEDGE BASE

## OVERVIEW

`wiki/` is the normalized, queryable legal knowledge graph rendered by the site builder.

## STRUCTURE

`guides/` combines related reasoning; `concepts/`, `rules/`, `cases/`, `laws/`, `history/`, `discussions/`, `interpretations/`, and `fact_patterns/` hold typed entities; `logs/` holds append-only operational history.

## WHERE TO LOOK

- Start with `index.md` and `guides/` for user-facing navigation.
- Use `rules/` for issue/elements/exceptions/conclusion reasoning and `fact_patterns/` for application contexts.
- Use `laws/`, `cases/`, and `interpretations/` for authority-bearing entities.
- Link claims to evidence blocks with stable `^claim-id` anchors and source locators.

## CONVENTIONS

- Preserve canonical IDs; use typed relations and `id_aliases` for compatibility.
- Keep collection `status` separate from `legal_status` and include temporal applicability where relevant.
- Every substantive conclusion should expose authority, evidence, provenance, and verification metadata.
- Author with the v1.4 template/schema; compatibility fields are migration concerns, not new authoring defaults.

## ANTI-PATTERNS

- Do not copy raw documents into `wiki/`.
- Do not make unsupported legal claims or leave evidence links implicit.
- Do not manually maintain generated navigation, graph, search, or site output.
