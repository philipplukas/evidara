# Security & Tenancy

## Overview

Evidara separates **who may see what** along corpus, tenant, and scope boundaries. Enforcement is shared across the control plane, processing, and search paths — not only in the UI.

## Tenancy model

| Concept | Role |
|---------|------|
| `tenant_id` | Isolates private corpora and licensed content. |
| `corpus_id` | Governs a logical collection of documents and indexing partitions. |
| `scope_type` | Declares visibility semantics (`global_public`, `tenant_private`, `tenant_shared`). |

Canonical definitions and examples appear in `contracts/` and [Boundary Contracts](boundary-contracts.md) (scope model).

## Boundary expectations

- **platform-control** — Authenticates operators; persists governance state. Must not leak tenant-private configuration across tenants.
- **document-intelligence** — Processing and published surfaces must carry stable tenant/corpus/scope metadata so downstream reads can filter consistently.
- **legal-search** — Every search and document-detail path must apply tenant and corpus filters derived from authenticated identity and routing rules. OpenSearch is not a security boundary by itself.

## Document Service (read API)

The Document Service (`contracts/api/document-intelligence.openapi.yaml`) must enforce the same visibility rules as the BFF: only published rows the caller is allowed to see. Prefer **caller identity or service-to-service credentials** that map to tenant/corpus scope; avoid anonymous broad access to Delta-backed rows.

## Secrets & credentials

- Runtime secrets live in the secret manager / deployment layer described in [Infrastructure Overview](../setup/infrastructure-overview.md), not in git.
- **Aspirational, not built:** JWT verification in `legal-search/api` does not exist today —
  the only guard is `ApiKeyGuard` (`src/core/auth/api-key.guard.ts`), and the browser is
  never authenticated (the BFF injects a server-held `X-API-Key`). User identity, the
  signed-assertion seam that would carry it to the backends, and the verification keys
  this line describes are designed in
  [ADR-0038: User identity, roles, and genuine operator attribution](../adr/0038-user-identity-and-operator-attribution.md)
  (Proposed). Today's enforced model is [ADR-0020](../adr/adr-0020-api-authentication.md).

## Related decisions

- [ADR-0020: API Authentication](../adr/adr-0020-api-authentication.md) (what is enforced today)
- [ADR-0038: User Identity & Operator Attribution](../adr/0038-user-identity-and-operator-attribution.md) (Proposed)
- [ADR-0004: Contract Strategy](../adr/0004-contract-strategy.md)
- [ADR-0010: Document Content Format](../adr/0010-document-content-format.md) (Docling and read boundaries)
