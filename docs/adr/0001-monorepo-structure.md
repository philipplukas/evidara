# ADR-0001: Monorepo Structure

## Status

Accepted

## Date

2026-03-28

## Context

Evidara consists of multiple components (platform-control, document-intelligence, legal-search) that share contracts, infrastructure definitions, and documentation. We need to decide how to organize the source code.

Options considered:
1. **Monorepo** — all components in one repository with top-level domain folders.
2. **Multi-repo** — separate repositories per component.
3. **Hybrid** — core in one repo, some components separate.

## Decision

Use a **monorepo** with top-level domain folders.

```
evidara/
  platform-control/
  document-intelligence/
  legal-search/
  contracts/
  infra/
  docs/
```

## Rationale

- **Atomic changes across contracts and consumers.** When a contract changes, the producing and consuming code can be updated in the same PR.
- **Shared visibility.** All contributors can see the full system, reducing knowledge silos.
- **Simplified governance.** One set of branch protections, CODEOWNERS, and CI configuration.
- **Contract co-location.** Contracts live alongside the components that produce and consume them.
- **Early-stage simplicity.** With a small team, multi-repo overhead is not justified.

## Consequences

- CI must support selective builds (only build/test what changed).
- CODEOWNERS must enforce per-component review.
- Clear folder-level boundaries must be maintained to prevent coupling.
- If the team grows significantly, the monorepo decision should be revisited.
