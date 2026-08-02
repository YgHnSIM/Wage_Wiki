# TEMPLATES KNOWLEDGE BASE

## OVERVIEW

Templates provide the authoring surface for new typed wiki entities and preserve the v1.4 metadata shape.

## WHERE TO LOOK

- `frontmatter-v1.4.md`: canonical current frontmatter template.
- Type-specific templates: use when creating a Rule, Case, Law, Guide, Interpretation, or related entity.
- Older templates: reference only for migration compatibility, not new documents.

## CONVENTIONS

- Keep placeholders explicit and aligned with `schemas/` vocabulary.
- Include provenance, authority, evidence, verification, and temporal fields when the entity type requires them.
- Prefer stable IDs and typed relation blocks over ad hoc `related_*` fields.

## ANTI-PATTERNS

- Do not encode fabricated legal facts in templates.
- Do not make v1.3 fields the default for new authoring.
- Do not change a template without checking frontmatter validation and representative site rendering.
