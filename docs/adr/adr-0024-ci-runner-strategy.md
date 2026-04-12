# ADR-0024: Phased CI Runner Strategy for Evidara

## Status

Accepted

## Date

2026-04-12

## Context

Evidara's CI footprint spans a few distinct runner needs:

- generic Node/Python bootstrap jobs for product and docs validation
- browser and integration jobs that need more memory, longer wall time, or Playwright/browser setup
- Docker-heavy image build jobs that are materially different from ordinary CI
- lightweight smoke and verification workflows used to prove runner assumptions before a broader migration

The repository currently uses a bridge policy while the long-term self-hosted runner platform is being established. The operational version of that policy lives in [CI Actions duration metrics and runner tuning](../runbooks/ci-actions-duration-metrics.md), but the repo needs a durable architecture decision that says what the end state is and how to get there safely.

The main constraint is that the legacy VM-based runner path should not be treated as the final target. We need a migration that is safe to execute in phases, keeps specialized Docker workloads separate, and only retires the old VM runners after the new pools have been proven with smoke coverage and representative jobs.

## Decision

Evidara will use a phased migration to an Ubuntu-compatible self-hosted runner tier, exposed through the existing light/heavy org variable pattern.

### Final target

- `LIGHT_RUNNER_RUNS_ON_JSON` maps to the self-hosted pool for generic Node/Python CI and smaller validation jobs.
- `HEAVY_RUNNER_RUNS_ON_JSON` maps to the self-hosted pool for browser, integration, and other higher-resource validation jobs.
- Specialized Docker or privileged image jobs remain in their own pool and are not folded into the generic light/heavy migration.

### Migration phases

1. **Smoke workflows**
   - Validate runner assumptions with small smoke workflows before broad cutover.
   - Treat smoke coverage as the acceptance gate for new pool behavior.

2. **Migrate light CI jobs**
   - Move the smallest, most deterministic CI jobs first.
   - Prefer fmt, unit tests, and simple validation workloads.

3. **Migrate heavy browser/integration jobs**
   - Move browser-driven and higher-resource jobs only after the light pool has proven stable.
   - Keep these jobs isolated from the light pool so queue pressure and failure modes stay easier to reason about.

4. **Keep special Docker jobs separate**
   - Preserve a separate pool or label set for Docker-heavy and privileged image workflows.
   - Do not force image builds into the generic light/heavy runner pools.

5. **Retire old VM-runner usage only after proof**
   - Remove the legacy VM-based runner usage only after the new pools have passed smoke coverage and representative workloads.
   - If the new pools regress, prefer fixing the pool or splitting labels before expanding back to the old VM path.

### Rollout rules

- Switch org variables first rather than hardcoding new labels across many workflows.
- Keep generic Node/Python bootstrap jobs on GitHub-hosted Linux only while the new self-hosted path is still being proven.
- Treat runner class boundaries as policy, not incidental workflow trivia.

## Consequences

### Positive

- The target state is explicit and reviewable instead of being implied by scattered workflow comments.
- Runner migration can proceed in small, reversible slices.
- Browser, Docker, and generic CI workloads stay separated, which reduces cross-coupling and queue contention.

### Negative

- The repo now has to maintain an intentional bridge period while the new pool proves itself.
- Some jobs may remain on GitHub-hosted Linux longer than ideal if the new self-hosted tier does not yet satisfy their bootstrap requirements.

### Neutral

- Existing workflow comments and the CI runbook remain the operational details for day-to-day maintenance.
- The ADR does not change any workflow behavior by itself; it only documents the policy the workflows should converge on.

## Alternatives Considered

### Nix-native CI rewrite on the legacy VM runners

Rejected. It would rework too many workflows around runner-specific assumptions and leave the repo with a bespoke CI shape that is harder to staff and evolve.

### Permanent GitHub-hosted CI

Rejected. It would avoid the migration work but give up the existing light/heavy runner abstraction and the operational control that self-hosted runners are intended to provide.

### Keep the legacy VM runners indefinitely

Rejected. That would defer the underlying policy decision instead of providing a path to a more durable runner platform.

## References

- [CI Actions duration and runner tuning](../runbooks/ci-actions-duration-metrics.md)
- [Repository structure](../architecture/repository-structure.md)
- [Evidara documentation home](../index.md)
