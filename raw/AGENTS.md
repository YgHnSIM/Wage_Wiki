# RAW CORPUS KNOWLEDGE BASE

## OVERVIEW

`raw/` stores original legal and labor materials used as evidence. It is an immutable, append-oriented corpus.

## STRUCTURE

| Directory | Material |
|---|---|
| `laws/` | Statutes, regulations, ordinances, amendments |
| `cases/` | Court decisions and case materials |
| `interpretations/` | Administrative interpretations, guidance, notices |
| `company_norms/` | Employment rules, contracts, company norms |
| `research_press/` | Research, press, and contextual material |

## CONVENTIONS

- Route new root-level files into the best typed subdirectory before extraction.
- Preserve bytes, filename meaning, and source provenance; path moves are logged as routing actions.
- Deduplicate only when canonical identity and content are confidently established; retain the canonical raw source and update references.
- Use the final raw path in `related_raw`, `Source`, and `Target` references.

## ANTI-PATTERNS

- Never edit raw text to fix a typo or normalize formatting.
- Never replace a raw document with a summary or derived markdown.
- Never delete an uncertain duplicate without recording the decision in the project log.
