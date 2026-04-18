# ADR-0026: `authority_id` / `jurisdiction_id` naming policy

Status: Accepted
Date: 2026-04-18
Deciders: Platform / Contracts
Related: ADR-0004 (contract strategy), ADR-0012 (layered contract governance)

## Context

In January 2026 commit `9549fba` (merged via #241) renamed the Swiss
authority IDs in `platform-control/seeds/reference/authorities.yaml`
from a flat scheme (`auth_fedlex`, `auth_bger`, `auth_bvger`) to a
country-prefixed scheme (`auth_ch_fedlex`, `auth_ch_bundesgericht`, …)
and dropped `jur_ch_federal` from `jurisdictions.yaml`. The PR touched
the seed only; roughly twenty downstream consumers were not updated,
including:

- `contracts/examples/**/*.json`
- `document-intelligence/tests/golden/**/*.json` and the
  canonical resolver map in `document-intelligence/src/.../jurisdiction.py`
- `platform-control/tests/fixtures/**/*.json`
- live-acquisition scripts (`scripts/ch-fedlex-fast-loop.sh`)
- canary workflows (`.github/workflows/*.yml`)
- the `scripts/check_country_overlay_files.py` validator, whose
  comments still documented the flat scheme as correct — so the
  validator silently contradicted the seed it was checking.

The drift was not surfaced by any contract or unit test, because no
test asserted seed / downstream referential integrity.

At the same time the repository has two files claiming canonicity for
the same classes of IDs:

- `platform-control/seeds/reference/{authorities,jurisdictions}.yaml`
  (used by the seeding and reference-data services)
- `platform-control/src/platform_control/hierarchies/{authorities,jurisdictions}.yaml`
  (older, used by the hierarchy-sync service and overlay loader)

Two canonical sources for the same ID class is the structural cause of
this drift and needs to be addressed alongside the naming policy.

## Decision

### 1. IDs are contracts, not labels

Once an `authority_id` or `jurisdiction_id` appears in any of the
following durable surfaces, renaming it is a **data migration**, not
a refactor:

- `contracts/examples/**/*.json`
- `document-intelligence/tests/golden/**/*.json`
- `platform-control/tests/fixtures/**/*.json`
- `scripts/**.sh` (live-acquisition scripts against real APIs)
- `.github/workflows/**.yml` (canary and scheduled workflows)
- the canonical resolver maps under `document-intelligence/src/`

Renames must ship in a **dedicated PR labeled `ids-migration`** that:

- updates the seed and every downstream caller atomically;
- keeps a deprecation alias for any ID already persisted in a live
  database, for at least one release window before the old ID is
  removed from seed data; and
- is reviewed as a data migration, not a stylistic change.

### 2. Authority naming rule

- **`auth_<proper-noun>`** when the publisher is a globally-unique
  proper noun. Examples: `auth_fedlex`, `auth_bger`, `auth_bvger`,
  `auth_bundesrecht`. A country prefix is redundant and stylistically
  noisy for these.
- **`auth_<country>_<leaf>`** when the leaf collides across countries.
  Administrative-court abbreviations (`vwgh`, `vwger`, `bverwg`) are
  the canonical example; use `auth_at_vwgh`, `auth_de_bverwg`.
- **`auth_<subdivision>_<leaf>`** for cantonal, Bundesland, or Land
  publishers where the subdivision disambiguates. Examples:
  `auth_zh_admin`, `auth_by_staatskanzlei`.

Rule of thumb: *if practitioners speak the name aloud without the
country qualifier, drop it from the ID.*

### 3. Jurisdiction naming rule

- **`jur_<iso-2>`** for country-level jurisdictions (e.g. `jur_ch`,
  `jur_de`).
- **`jur_<iso-2>_federal`** for the federal/confederation scope where
  it is distinct from the country as a whole (`jur_ch_federal`,
  `jur_de_federal`, `jur_at_federal`).
- **`jur_<iso-2>_<subdivision-code>`** for cantons, Bundesländer,
  Länder and regions. Subdivision codes follow ISO 3166-2 lowercased
  (`jur_ch_zh`, `jur_de_by`, `jur_at_bgld`, `jur_it_25`).

### 4. One canonical source per ID class

`platform-control/seeds/reference/authorities.yaml` and
`platform-control/seeds/reference/jurisdictions.yaml` are the single
source of truth. The older files at
`platform-control/src/platform_control/hierarchies/{authorities,jurisdictions}.yaml`
must be **retired or demoted to a generated mirror** of the reference
seeds. Having two files each claim canonicity is the structural cause
of this class of drift and is not acceptable long-term.

Retiring or demoting the legacy `hierarchies/*.yaml` files is
**deferred to a follow-up PR** (scoped out of this ADR to keep the
policy landable independently).

### 5. Enforcement

Every `authority_id` / `jurisdiction_id` string appearing in the
durable surfaces listed in §1 must resolve against the reference seeds
(or a narrowly-scoped, commented known-drift allowlist with a ratchet
check). This invariant is enforced by
`platform-control/tests/unit/test_seed_id_consistency.py`, introduced
by **PR #266**. The test runs in the `scraping-qa` CI job and would
have caught the drift from #241 pre-merge.

The allowlist is intentionally narrow and each entry is commented with
the reason. The ratchet check fails if an allowlist entry stops being
needed — preventing the list from accumulating stale entries.

## Alternatives considered

### A. Country-prefixed scheme for every authority

A uniform `auth_<country>_<leaf>` rule for every authority, including
globally unique publishers like Fedlex and BGer.

Rejected: makes the common case (`auth_fedlex`) longer than the
disambiguated case (`auth_zh_admin`) without information gain; forces
a rename every time we add a country that has the same leaf (none
currently); and — crucially — this is the scheme commit `9549fba`
adopted, which triggered the drift the policy exists to prevent.

### B. Flat scheme only (no subdivisions)

`auth_<leaf>` everywhere, relying on the leaf to be globally unique.

Rejected: cantonal / Bundesland publishers routinely share short leaf
names (`admin`, `staatskanzlei`, `justiz`). The subdivision prefix is
load-bearing for those IDs.

### C. Policy without an enforcement test

Document the convention in `CONTRIBUTING.md` and rely on code review.

Rejected: this is effectively what we had before #241. Code review
missed a single-commit rename of twenty cross-component references. A
programmatic gate is the only scalable check.

### D. Make the existing validator check seed referential integrity

Extend `scripts/check_country_overlay_files.py` rather than adding a
new pytest.

Rejected: the validator is overlay-scoped and runs in a different CI
job. The pytest lives alongside the seed data it checks, can run under
`pytest` locally, and participates in the scraping-qa gate without
extending an already-complex shell script.

## Consequences

**Positive:**

- Renames are explicit data migrations with a deprecation window, not
  seed-file refactors.
- `platform-control/seeds/reference/*` is unambiguously canonical.
- The enforcement test shipped in #266 makes silent drift impossible —
  any new `authority_id` / `jurisdiction_id` in a durable surface must
  resolve in the seed or be explicitly allowlisted with a comment.
- Short, readable IDs for well-known publishers are preserved
  (`auth_fedlex`, `auth_bger`) while still giving cantonal / Land
  publishers a disambiguator.

**Negative:**

- The known-drift allowlist in `test_seed_id_consistency.py`
  (pre-existing AT and DE federal entries, scraping-baseline fixture
  placeholders) carries technical debt that must be worked down.
  Follow-up `ids-migration` PRs track this.
- The legacy `platform-control/src/platform_control/hierarchies/*.yaml`
  files remain canonical for their existing consumers until the
  retirement follow-up lands. Until then, any PR that adds a new
  authority or jurisdiction must consider both files.

## Implementation

- **This ADR:** docs-only. Codifies the policy.
- **Enforcement test:** `platform-control/tests/unit/test_seed_id_consistency.py`,
  shipped in **PR #266** alongside the first application of this
  policy (the CH reconciliation back to the flat scheme and the
  restoration of `jur_ch_federal`).
- **Legacy-hierarchies retirement:** deferred follow-up, tracked
  against issue #264 after this ADR lands.
- **AT / DE federal reconciliation:** deferred `ids-migration` PRs,
  surfaced by the allowlist entries in the enforcement test.

## References

- Issue #264 — policy proposal.
- PR #241 and commit `9549fba` — the original drift.
- PR #266 — CH reconciliation + enforcement test.
- `platform-control/seeds/reference/authorities.yaml`
- `platform-control/seeds/reference/jurisdictions.yaml`
- `scripts/check_country_overlay_files.py`
