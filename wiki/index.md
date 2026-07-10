# Wage Wiki Dashboard

이 문서는 Dataview 쿼리 기반 대시보드입니다. 수동 목록을 추가하지 않습니다.

## All Entities

```dataview
TABLE entity_type, status, legal_status, ingestion_status, primary_authority_id, authority_level, as_of_date, last_checked
FROM "wiki"
WHERE entity_type
SORT entity_type ASC, title ASC
```

## Verified Current Knowledge

```dataview
TABLE entity_type, primary_authority, authority_ids, effective_from, last_verified
FROM "wiki"
WHERE entity_type AND status = "verified" AND legal_status = "current"
SORT entity_type ASC, title ASC
```

## Review Queue

```dataview
TABLE entity_type, ingestion_status, primary_authority, review_cycle, last_checked, review_trigger
FROM "wiki"
WHERE entity_type AND (status = "review" OR ingestion_status = "linked")
SORT last_checked ASC, entity_type ASC
```

## Future Authorities

```dataview
TABLE entity_type, effective_from, enforcement_weight, review_trigger
FROM "wiki"
WHERE entity_type AND legal_status = "future"
SORT effective_from ASC
```

## Rules Without Authority

```dataview
TABLE status, primary_authority, related_cases, related_laws, related_raw
FROM "wiki/rules"
WHERE entity_type = "rule"
WHERE !primary_authority_id OR length(default(authority_ids, [])) = 0
SORT file.name ASC
```

## Orphan Candidates

```dataview
TABLE entity_type, status, ingestion_status, last_updated
FROM "wiki"
WHERE entity_type
WHERE length(default(related_concepts, [])) = 0
  AND length(default(related_rules, [])) = 0
  AND length(default(related_cases, [])) = 0
  AND length(default(related_laws, [])) = 0
  AND length(default(related_interpretations, [])) = 0
  AND length(default(related_fact_patterns, [])) = 0
  AND length(default(relations, [])) = 0
SORT entity_type ASC, file.name ASC
```

## Active Conflicts

```dataview
TABLE entity_type, conflict_type, conflict_resolution, conflict_resolution_note, last_updated
FROM "wiki"
WHERE conflict_status = "active"
SORT conflict_resolution ASC, last_updated ASC
```

## Case Source Gaps

```dataview
TABLE status, source_availability, source_availability_note, source_urls, last_checked
FROM "wiki/cases"
WHERE entity_type = "case" AND source_availability != "available"
SORT source_availability ASC, decision_date DESC
```

## Ingestion Queue

```dataview
TABLE entity_type, ingestion_status, related_raw, last_updated
FROM "wiki"
WHERE ingestion_status = "imported" OR ingestion_status = "extracted" OR ingestion_status = "linked"
SORT ingestion_status ASC, last_updated ASC
```
