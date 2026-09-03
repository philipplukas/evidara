# Parallel work streams (by component)

Use this when several people or initiatives move at once. The goal is **parallel PRs with minimal merge friction**: each stream stays mostly in its own tree; shared seams are owned explicitly.

## Streams that can run in parallel

| Stream | Owns (typical) | Contract / surface |
|--------|----------------|-------------------|
| **legal-search** | `legal-search/**` | `contracts/api/legal-search.openapi.yaml` when the BFF contract changes |
| **platform-control** | `platform-control/**` | `contracts/api/platform-control.openapi.yaml` when that API changes |
| **document-intelligence** | `document-intelligence/**` | Pipeline- or event-related schemas under `contracts/` when those change |
| **infra** | `infra/**`, deployment configs | Environment and resource wiring |
| **docs / runbooks** | Scoped docs (one initiative per PR or file when possible) | Must match shipped behavior |

**contracts** is not usually a standalone dev stream: whoever changes an API updates the spec; consumers regenerate clients (see AGENTS.md contract rules).

## Serialize or single-owner (do not parallelize the same change)

- **Same OpenAPI file** — one stream leads; others implement after merge or rebase onto it.
- **Same Alembic migration / shared ORM model** — one owner for that migration batch.
- **Cross-service behavior** — agree contract (or event shape) first, then implement in each component in parallel.

## Day-to-day habits

- Prefer **small PRs to `main`** per stream; avoid long-lived integration branches unless unavoidable.
- If two streams need the same API shape, land a **contract-first PR** (spec + minimal validation), then parallel implementation PRs.
- Update **smoke scripts and runbooks** when operator entrypoints or recovery steps change (same PR as the behavior or immediately after).

## Related

- MacConfig / Kubernetes migration lanes (GitOps, Argo, Terraform slimming): [Migration parallel workstreams](../migration/parallel-workstreams.md)
- Max concurrency, stale-branch refresh policy, and serialization gates: [Max parallel execution](max-parallel-execution.md)
- The same seams applied to multi-agent orchestration scripts: [Agent workflows](agent-workflows.md)
- Change classification and required sync checks: [AGENTS.md](../../AGENTS.md)
- Contract location (monorepo root only): [ADR-0004: Contract strategy](../adr/0004-contract-strategy.md)
