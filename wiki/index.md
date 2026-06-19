# Wage Wiki Dashboard

이 문서는 Dataview 쿼리 기반 대시보드입니다. 수동 목록을 추가하지 않습니다.

## All Entities

```dataview
TABLE entity_type, status, ingestion_status, primary_authority, authority_level, enforcement_weight, last_updated
FROM "wiki"
WHERE entity_type
SORT entity_type ASC, title ASC
```

## Rules Without Authority

```dataview
TABLE status, primary_authority, related_cases, related_laws, related_raw
FROM "wiki/rules"
WHERE entity_type = "rule"
WHERE !primary_authority OR (length(default(related_cases, [])) = 0 AND length(default(related_laws, [])) = 0)
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
  AND length(default(related_fact_patterns, [])) = 0
SORT entity_type ASC, file.name ASC
```

## Active Conflicts

```dataview
TABLE entity_type, conflict_type, conflict_resolution, conflict_resolution_note, last_updated
FROM "wiki"
WHERE conflict_status = "active"
SORT conflict_resolution ASC, last_updated ASC
```

## Ingestion Queue

```dataview
TABLE entity_type, ingestion_status, related_raw, last_updated
FROM "wiki"
WHERE ingestion_status = "imported" OR ingestion_status = "extracted" OR ingestion_status = "linked"
SORT ingestion_status ASC, last_updated ASC
```

