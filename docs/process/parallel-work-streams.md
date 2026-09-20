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
- **The platform-control API version** — see below. One lane at a time, and it is not a convention you can work around.

### The platform-control API version is a single-owner lane

`API_VERSION` in `platform-control/src/platform_control/openapi.py` moves with **three** files that
must agree, by design:

| File | Key | Enforced by |
|---|---|---|
| `platform-control/src/platform_control/openapi.py` | `API_VERSION` | — it is the source |
| `contracts/api/platform-control.openapi.yaml` | `info.version` | `scripts/generate_platform_control_contract.py` (ADR-0034 drift gate) |
| `contracts/manifest.yaml` | `apis.platform_control.version` | `scripts/check_contract_manifest.py` |

Two PRs that both change the platform-control API surface therefore collide twice over: textually on
each of those three lines, and semantically, because two PRs that pick the *same* successor merge
cleanly and then describe two different surfaces under one number.

**Measured, 2026-09-19.** While both were open, #1041 and #1042 each moved `API_VERSION` from
`0.33.0` to `0.34.0`, and each also edited `contracts/api/platform-control.openapi.yaml` and
`contracts/manifest.yaml`. They landed hours apart, and the second had to rebase and re-pick its
successor. That is the lane being run by hand under time pressure; writing it down is cheaper than
rediscovering it.

**The rule.** At most one in-flight PR changes the platform-control API surface. Before you open the
second one:

1. Check for an open PR that touches `platform-control/src/platform_control/openapi.py` or
   `contracts/api/platform-control.openapi.yaml`:
   `gh pr list --state open --search "openapi.py in:path"`.
2. If there is one, that lane leads. Land it, then rebase and **regenerate** — do not hand-pick a
   successor number. `python3 scripts/bump_contract_version.py --minor --api --summary "..."`
   computes it from what is on your branch.
3. Name the coordinating PR in the "Work stream coordination" section of your own PR.

**This is deliberately not the #913 treatment.** #913 moved `contracts/manifest.yaml`'s *top-level*
`version` into per-PR changesets under `contracts/changes/`, because that scalar serialised PRs that
had nothing to do with each other. `apis.platform_control.version` is different: it must equal the
**generated** spec's `info.version`, which is a committed file, so the number cannot be deferred to
a release without either shipping a stale committed spec or moving ADR-0034's drift gate out of the
PR that changed the API. `scripts/contract_changesets.py` says so in its own docstring, and
`scripts/release_contract_version.py` deliberately does not touch the key.

The conflict here is **inherent to two concurrent edits of one API surface** — those two PRs would
have conflicted inside the generated spec's paths and schemas regardless of the version line.
What #913 removed was accidental contention; this is the real thing, and serialising it is the
honest answer until the surface is split.

`scripts/check_api_version_lane.py` keeps this section pointed at the real constant: move
`API_VERSION` and the rule goes red rather than quietly describing a file that no longer exists.

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
