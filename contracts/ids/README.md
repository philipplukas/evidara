# Evidara ID Conventions

## Overview

All entities in Evidara are identified by string IDs. This document defines the naming conventions, formatting rules, and uniqueness expectations for each ID family.

## ID Families

| ID | Owner | Format | Example |
|----|-------|--------|---------|
| `source_id` | platform-control | `src_{ulid}` | `src_01HZXK7V3QMJY4T5N2P8R6W9` |
| `source_version_id` | platform-control | `sv_{ulid}` | `sv_01HZXK8A2BMNE6G4R7J3K9L5` |
| `run_id` | platform-control | `run_{ulid}` | `run_01HZXK9C4DNPF8H6T2M5Q7W3` |
| `artifact_id` | platform-control | `art_{ulid}` | `art_01HZXKA5EQRSG9J3V4N7P8X2` |
| `document_id` | document-intelligence | `doc_{ulid}` | `doc_01HZXKB7FSTUH0K5W6P9R2Y4` |
| `section_id` | document-intelligence | `sec_{ulid}` | `sec_01HZXKC9GUVWI1L7X8Q3S4Z6` |
| `citation_id` | document-intelligence | `cit_{ulid}` | `cit_01HZXKD0HVWXJ2M8Y9R4T5A7` |
| `workflow_run_id` | platform-control | `wfr_{ulid}` | `wfr_01HZXKE2IWXYK3N9Z0S5U6B8` |

## Format Rules

- **Prefix:** Each ID has a short, lowercase prefix indicating the entity type, followed by an underscore.
- **Body:** ULIDs (Universally Unique Lexicographically Sortable Identifiers) are recommended. They are sortable by creation time, globally unique, and URL-safe.
- **Case:** All lowercase.
- **Character set:** Alphanumeric and underscores only.

## Uniqueness

- IDs are **globally unique within their family.** No two sources share a `source_id`, no two documents share a `document_id`, etc.
- ULIDs provide sufficient uniqueness for distributed ID generation without coordination.

## Ownership

- The component that **creates** an entity **assigns** its ID.
- IDs are **carried through** as references when crossing boundaries (e.g., `source_id` appears in document records for lineage).
- IDs are **never reassigned or reused.**

## Future Considerations

- Generated client libraries may enforce ID format validation.
- ID prefixes allow quick identification of entity type from any ID string.
- If ULIDs prove insufficient, the format can evolve with a documented migration.
