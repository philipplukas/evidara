# ADR-0030: Acquisition provider enablement lifecycle

Status: Accepted
Date: 2026-07-13
Deciders: Contracts / Platform
Related: ADR-0025 (portal HTTP provider strategy), ADR-0026 (`authority_id` / `jurisdiction_id` naming policy), ADR-0009 (FastAPI conventions)

## Context

platform-control acquires legal content through a growing family of
providers (Fedlex SPARQL, deterministic HTTP, RIS OGD, Légifrance,
EUR-Lex SPARQL, CH court decisions, and the sub-federal portal providers
from ADR-0025). Providers land in two very different states:

- **Scaffolds** — the provider class is registered so blueprint templates
  that reference it parse, but `start_run` is a stub. The target API
  contract may not be fully wired or mocked yet.
- **Implementations** — `start_run` is internally consistent and covered
  by mocked tests against the target API contract.

Separately, a provider being *implemented* is not the same as a template
being *safe to run live*. Live acquisition touches third-party
infrastructure under a compliance policy, so the decision to go live is an
operator judgement backed by evidence, not a code property.

We need one coherent lifecycle that (a) lets scaffolds be committed and
referenced without risking an accidental live run, (b) makes the
scaffold-vs-live distinction explicit in code, (c) validates provider
configuration at build time rather than at run time, and (d) defines how a
template crosses from disabled to live.

## Decision

Adopt a single enablement lifecycle with four load-bearing mechanisms.

### 1. Provider protocol with an explicit `live_ready` flag

The `AcquisitionProvider` protocol
([`platform-control/src/acquisition_core/providers.py`](../../platform-control/src/acquisition_core/providers.py))
carries a `live_ready: bool` class attribute that encodes the
scaffold-vs-implementation distinction:

- `live_ready = False` — `start_run` is a stub (typically raises
  `NotImplementedError`). The provider is registered only so templates
  referencing it parse.
- `live_ready = True` — `start_run` performs real work and is covered by
  mocked tests against its target API contract.

`ProviderRegistry.live_ready_names()` enumerates the implemented
providers for operator read models and readiness checks.

### 2. Two-key lock for launching a run

Production-readiness lives on the blueprint template, not the provider. A
run may launch only when **both** keys are turned:

- `provider.live_ready is True` (the provider is implemented), **and**
- `template.enabled is True` in
  [`source_blueprints.yaml`](../../platform-control/src/platform_control/hierarchies/source_blueprints.yaml)
  (the operator has accepted it for live acquisition).

Both keys are enforced in the run-launch path — `RunService._require_launchable()`,
called from `create_run()` (before the run row is persisted, so a
worker-backed dispatch cannot accept a run it can never run) and again from
`_dispatch_run()` (the last gate before any outbound request, covering the
scheduler, retry, and Temporal paths):

- **Provider key.** `ensure_live_ready()` (shared by
  `ProviderRegistry.require_live_ready()`, which resolves-then-checks for
  loader-style callers) raises `ProviderNotLiveReadyError` when the provider
  that will actually be called is a scaffold. Callers that only want to
  resolve-and-introspect keep using `resolve_for_spec()` /
  `resolve_for_version()`.
- **Template key.** A source version created from a blueprint records its
  `overlay_id` / `provider_template_id`, and the run-launch path re-reads that
  template's `enabled` flag from `source_blueprints.yaml`, raising
  `BlueprintTemplateNotEnabledError` unless it is `true`. Re-reading (rather
  than snapshotting at creation) makes `enabled: false` a kill switch: flipping
  a template off stops its existing source versions from dispatching. Versions
  built from a hand-written `acquisition_spec` carry no template, so only the
  provider key applies to them.

Both errors surface as HTTP 400, the same family as `ProviderConfigurationError`.
A `PENDING` run that the lock rejects is marked `FAILED` by the worker rather
than retried forever.

`ExecutionMode.SHADOW` versions are exempt: they are routed to the cassette
provider and replay fixtures, so no request reaches the portal the lock
protects — that is the rehearsal mode an operator uses *before* capturing
acceptance-run evidence.

Both keys default to the safe value (`live_ready = False`, `enabled`
absent/false), so new work is inert until deliberately turned on. Templates
state `enabled` explicitly, and a template may only be `enabled: true` if its
provider is `live_ready` — both invariants are asserted by
`tests/unit/test_blueprint_provider_parity.py`, and the lock itself by
`tests/unit/test_provider_enablement_lock.py` (#559).

### 3. AcquisitionSpec discriminated union with `extra="forbid"`

Every provider's configuration is a Pydantic v2 model discriminated on the
`provider` field, unioned as `AcquisitionSpec`
([`platform-control/src/platform_control/schemas/source.py`](../../platform-control/src/platform_control/schemas/source.py)).
`BaseAcquisitionSpec` sets `model_config = ConfigDict(extra="forbid")`, so
an unknown or misspelled key in a template is a validation error, not a
silently-ignored field. `parse_acquisition_spec()` is the single parse
entry point, and `check_country_overlay*.py` exercises it at build time
(and in the Docs-and-Contracts CI job) so a malformed template fails
before it can ever reach a run. This converts the class of
"operator misconfigured the template" failures that ADR-0025 flagged as a
run-time `ProviderConfigurationError` into a build-time parse error for
every field the spec declares.

### 4. Compliance tiers with authority-over-jurisdiction resolution

Politeness and retention are declared as reusable policies in
[`compliance_policies.yaml`](../../platform-control/src/platform_control/seeds/reference/compliance_policies.yaml)
across three tiers:

- **open-data** (Fedlex, RIS OGD) — `robots=ignore`, wide rate corridor,
  no retention floor.
- **public-official** (courts/gazettes without explicit terms) —
  `robots=strict`, ~10–20 rpm, 365-day retention.
- **restrictive** (anti-bot / unclear licence) — `robots=strict`, minimal
  rate, short retention.

`_resolve_policy_for_source()` in
[`compliance_policy_service.py`](../../platform-control/src/platform_control/services/compliance_policy_service.py)
resolves a source's policy **authority-level first, jurisdiction-level as
fallback**. This precedence is what lets one jurisdiction carry mixed
tiers: under `jur_ch_federal`, Fedlex legislation stays on the open-data
policy while the federal courts (`auth_bger`/`auth_bvger`/…) bind the
stricter `cp_ch_court_decisions`, because the authority override wins over
the jurisdiction default.

### 5. Acceptance-run → evidence → flip-live workflow

A template crosses from `enabled: false` to live through an operator
workflow, not a code change:

1. Run the provider's acceptance harness against an environment
   (e.g. [`scripts/ch-fedlex-fast-loop.sh`](../../scripts/ch-fedlex-fast-loop.sh);
   the parallel `scripts/ch-bger-fast-loop.sh` court harness lands with the
   `ch_court_decisions` provider), which drives a narrow preview run and
   asserts provider capture, the
   downstream DI lifecycle (`accepted` → `processing` → `canonical_ready`
   → `document.processed`), and content-quality gates, emitting a `pass`
   verdict.
2. Persist the evidence bundle under
   [`docs/runbooks/evidence/`](../runbooks/evidence/README.md)
   (the harness `--copy-evidence` flag writes it there).
3. With a `pass` verdict as justification, the operator flips
   `provider.live_ready` (if still a scaffold) and `template.enabled: true`
   — turning both keys of the lock.

The two fast-loop scripts hardcode `auth_fedlex` / `jur_ch_federal` /
`auth_bger`; renames of those IDs must keep the harnesses functional
(see ADR-0026).

## Alternatives considered

### A. Single boolean (template `enabled` only)

Drop `live_ready` and gate solely on `template.enabled`. Rejected: a
scaffold whose `start_run` is a stub would fire the moment an operator
enabled its template, with no signal that the provider code is not
actually implemented. The two keys separate "code is ready" from
"operator accepts it", and each has a distinct owner.

### B. Run-time-only config validation

Keep validating provider config when `start_run` executes (the ADR-0025
status quo). Rejected: misconfiguration then surfaces only during a live
run against a third party. `extra="forbid"` + a build-time parse guard
moves the whole declared-field class of errors left to CI.

### C. Per-provider compliance settings inline on the template

Put rate/retention on each template instead of a shared policy resolved by
authority/jurisdiction. Rejected: duplicates politeness config per
template and loses the single-source-of-truth tiers; the
authority-over-jurisdiction resolution already expresses mixed tiers
within one jurisdiction without per-template duplication.

## Consequences

**Positive:**

- Scaffolds are safe to commit and reference; the two-key lock makes an
  accidental live run structurally impossible.
- The scaffold-vs-live boundary is explicit in code (`live_ready`) and the
  live decision is explicit in config (`enabled`), with separate owners.
- Template misconfiguration fails in CI, not against a live third party.
- One jurisdiction can carry mixed compliance tiers per authority.
- Live-enablement is an auditable operator workflow with evidence under
  version control.

**Negative:**

- Two keys mean two places to change when genuinely going live; an
  operator who flips only `enabled` on a still-scaffold provider gets a
  `ProviderNotLiveReadyError` rather than a run. This is intentional but is
  a footgun without the runbook.
- `extra="forbid"` makes spec evolution slightly stricter: adding a field
  to a template requires adding it to the spec model first.

## References

- [`platform-control/src/acquisition_core/providers.py`](../../platform-control/src/acquisition_core/providers.py)
  — protocol, `live_ready`, `ensure_live_ready` / `require_live_ready`.
- [`platform-control/src/platform_control/services/run_service.py`](../../platform-control/src/platform_control/services/run_service.py)
  — `_require_launchable()`, the run-launch enforcement point for both keys.
- [`platform-control/src/platform_control/services/source_blueprints.py`](../../platform-control/src/platform_control/services/source_blueprints.py)
  — `require_source_blueprint_enabled()`, the template-side key.
- [`platform-control/src/platform_control/schemas/source.py`](../../platform-control/src/platform_control/schemas/source.py)
  — `AcquisitionSpec` discriminated union, `extra="forbid"`,
  `parse_acquisition_spec`.
- [`platform-control/src/platform_control/hierarchies/source_blueprints.yaml`](../../platform-control/src/platform_control/hierarchies/source_blueprints.yaml)
  — `enabled` flag per template.
- [`platform-control/src/platform_control/seeds/reference/compliance_policies.yaml`](../../platform-control/src/platform_control/seeds/reference/compliance_policies.yaml)
  and [`compliance_policy_service.py`](../../platform-control/src/platform_control/services/compliance_policy_service.py)
  — tiers and `_resolve_policy_for_source` precedence.
- [CH acquisition coverage status and roadmap](../architecture/ch-acquisition-coverage-status.md).
- [Country rollout & drift-prevention backlog](../runbooks/country-rollout-drift-prevention-backlog.md).
