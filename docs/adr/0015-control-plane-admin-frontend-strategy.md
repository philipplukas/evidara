# ADR-0015: Control-Plane Admin Frontend Strategy

## Status

Accepted

**Implementation note:** The React-admin app in `platform-control/admin` is the **current** operator UI. Retool is retired for day-to-day work; archived artifacts live under `platform-control/retool/`. The Context and Decision sections below record the migration from the ADR-0006 Retool approach.

## Date

2026-04-03

## Context

ADR-0006 chose Retool for the first internal ops UI slice because it was the fastest way to stand up
operator workflows for sources, approvals, runs, and monitoring.

That choice helped define the initial control-plane shape, but it also introduced a long-term mismatch
with the way this repo is built:

- the team increasingly wants the admin UI to live in normal source control
- AI-assisted coding reduces the relative advantage of a low-code UI
- Retool still keeps the live app and resource model in Retool rather than in the repo
- the current Retool design depends on direct Postgres reads, which is not the right model for a
  fully code-managed browser app
- `legal-search` is explicitly reserved for external user-facing search, not internal operator flows

We need to decide the long-term admin frontend direction and where it belongs.

## Decision

- Evidara will move from Retool to a fully code-managed admin frontend.
- The admin frontend will live under `platform-control/admin`, not inside `legal-search`.
- The initial implementation will use **Next.js + React-admin**.
- `platform-control` will become the sole backend for the admin app. The browser will not read
  Postgres directly.
- Retool artifacts remain transitional until the React-admin app reaches parity for the main operator
  flows, then Retool should be retired.
- The first backend work for this migration is to add operator read APIs for data that Retool
  currently reads directly from Postgres, especially:
  - runs list
  - run captured resources
  - run raw artifacts
  - run provider jobs

## Consequences

### Positive

- The admin UI becomes a normal repo-native app that can be built, reviewed, tested, and changed
  with the same workflows as the rest of the codebase.
- AI coding can be applied directly to the admin frontend without Retool-specific assembly steps.
- The platform gets a cleaner architecture where the admin UI consumes supported APIs instead of
  reading the database directly.
- `legal-search` keeps its user-facing boundary and visual language.

### Negative

- The migration requires new read endpoints in `platform-control`, not just frontend work.
- React-admin introduces a new frontend framework and likely a different component stack than the
  current `legal-search` UI.
- Retool and React-admin will coexist for a period while parity is reached.

### Neutral

- Existing Retool artifacts remain useful as migration reference material, demo scaffolding, and a
  temporary fallback until the coded admin app is complete.

## Alternatives Considered

### Keep Retool as the long-term solution

Rejected because the team wants the admin UI fully code-managed in the repo, and AI-assisted coding
makes the low-code tradeoff less compelling than before.

### Put the admin UI inside `legal-search`

Rejected because it conflicts with the repo's component boundaries. `legal-search` is the external
search experience; internal ops workflows belong with `platform-control`.

### Build a custom Next.js admin app without React-admin

Rejected for the initial migration because React-admin gives faster scaffolding for resource-heavy
operator flows. We can still peel back toward lower-level customization later if needed.

## References

- [ADR-0006: Internal Ops UI Strategy](0006-internal-ops-ui-strategy.md)
- [Repository Structure](../architecture/repository-structure.md)
- [Platform Control](../components/platform-control.md)
- [Platform-Control React-Admin Migration](../components/platform-control-react-admin-migration.md)
