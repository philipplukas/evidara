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

### 1. Provider protocol with an explicit readiness state

> **Amended 2026-07-20 (#743/#735).** This section originally specified a
> `live_ready: bool`. That binary is superseded by a three-state
> `AcquisitionReadiness`; the reasoning is recorded in §6 below, and the
> boolean survives only as a derived projection.

The `AcquisitionProvider` protocol
([`platform-control/src/acquisition_core/providers.py`](../../platform-control/src/acquisition_core/providers.py))
carries an `AcquisitionReadiness` class attribute — the **code-owner key**:

- `SCAFFOLD` — `start_run` is a stub (typically raises `NotImplementedError`).
  The provider is registered only so templates referencing it parse. **Remedy:
  engineering.** No run of any mode may dispatch.
- `AWAITING_EVIDENCE` — `start_run` performs real work, is covered by tests
  against its target contract, and the provider can physically acquire its
  format — but no operator has captured an acceptance run yet. **Remedy: run the
  loop.** Only a `RunMode.ACCEPTANCE` run may dispatch.
- `LIVE` — acceptance evidence exists and was accepted. Runs dispatch once the
  config key is also open.

`live_ready` remains as a derived boolean (true only for `LIVE`) so existing
clients and the OpenAPI contract keep working; `provider_readiness()` also
accepts the legacy bool from third-party doubles and fails closed on anything
unrecognised.

`ProviderRegistry.live_ready_names()` enumerates only `LIVE` providers — an
*enabled* template must never reference one whose evidence nobody captured.
Operator read models resolve readiness per template through
`SourceService._provider_readiness()`.

### 2. Two-key lock for launching a run

Production-readiness lives on the blueprint template, not the provider. A
run may launch only when **both** keys are turned (with one narrow exception —
`RunMode.ACCEPTANCE`, see §6):

- the provider's readiness is `LIVE` (see §1; amended from
  `provider.live_ready is True` by #743), **and**
- `template.enabled is True` in
  [`source_blueprints.yaml`](../../platform-control/src/platform_control/hierarchies/source_blueprints.yaml)
  (the operator has accepted it for live acquisition).

Both keys are enforced in the run-launch path — `RunService._require_launchable()`,
called from `create_run()` (before the run row is persisted, so a
worker-backed dispatch cannot accept a run it can never run) and again from
`_dispatch_run()` (the last gate before any outbound request, covering the
scheduler, retry, and Temporal paths):

- **Provider key.** `ensure_launchable()` (renamed from `ensure_live_ready()`
  by #743; shared by `ProviderRegistry.require_live_ready()`, which
  resolves-then-checks for loader-style callers) raises
  `ProviderNotLiveReadyError` when the provider that will actually be called has
  a readiness the run's mode does not admit — naming *which* state blocked, since
  a scaffold and a provider awaiting evidence have different remedies. Callers that only want to
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
protects. That also means a SHADOW run proves nothing about the live portal and
**cannot serve as acceptance evidence** — capturing evidence is what
`RunMode.ACCEPTANCE` is for (§6).

Both keys default to the safe value (readiness `SCAFFOLD` — including for any
provider that declares nothing, or declares something unrecognised — and
`enabled` absent/false), so new work is inert until deliberately turned on.
Templates state `enabled` explicitly, and a template may only be `enabled: true`
if its provider is `LIVE` (not merely `AWAITING_EVIDENCE`: an enabled template
would dispatch production runs on evidence nobody captured) — both invariants are
asserted by
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
   `ch_court_decisions` provider), which drives a narrow run — `mode=acceptance`
   for a provider still awaiting evidence, since a preview run is subject to the
   same lock (see §6) — and asserts provider capture, the
   downstream DI lifecycle (`accepted` → `processing` → `canonical_ready`
   → `document.processed`), and content-quality gates, emitting a `pass`
   verdict.
2. Persist the evidence bundle under
   [`docs/runbooks/evidence/`](../runbooks/evidence/README.md)
   (the harness `--copy-evidence` flag writes it there).
3. With a `pass` verdict as justification, the provider's readiness moves to
   `LIVE` (a code change, if it was `AWAITING_EVIDENCE`) and the operator flips
   `template.enabled: true` from the admin — turning both keys of the lock.

A `pass` verdict is only justification for the gates that actually ran. Several
gates self-skip when they do not apply to a template (the title regex, the body
language hint, the indexed-language facet), and a skipped gate used to render as
an unqualified pass. The evidence markdown now carries a **Gate coverage**
section listing every skipped gate by name (`checks.skipped_gates` in
`summary.json`); read it before step 3 and treat a skipped gate as unverified,
not as verified-and-green (#744).

`scripts/ch-fedlex-fast-loop.sh` and `scripts/ch-fedlex-compose-e2e.sh` take the
corpus shape as flags — `--expect-content-type`, `--url-pattern`,
`--jurisdiction-id`, `--authority-id`, `--corpus-slug` — so a non-HTML or
non-federal corpus is measured against its own shape instead of being reported
as `provider_failed` for not being Fedlex. Their *defaults* are still
`auth_fedlex` / `jur_ch_federal`, and `scripts/ch-bger-fast-loop.sh` still
hardcodes `auth_bger`; renames of those IDs must keep the harnesses functional
(see ADR-0026).

### 6. `RunMode.ACCEPTANCE` — how a provider earns its first key

> **Added 2026-07-20 (#743/#735).**

The workflow in §5 assumed an acceptance run was possible on a locked template.
It was not. Traced on `main`:

- Acceptance evidence requires a run against the **live** portal. `SHADOW` is
  exempt from the lock (`run_service.py`) but routes to the cassette provider and
  replays fixtures, so it proves nothing about the live portal and cannot serve
  as evidence.
- Every non-SHADOW run — **including `mode=preview`** — passes
  `_require_launchable`, at creation and again at dispatch.
- That requires both keys. The code key was a class constant with no env or DB
  override.

So the evidence required the run, the run required the code key, and the code key
required the evidence. A provider could never earn its own first key without an
engineer shipping a code change. Fedlex never hit this because its templates were
already enabled — the workflow had never been exercised on a genuinely locked
template, which is why the deadlock survived unnoticed.

That is not merely inconvenient. #628 measures the cost of the **Nth** source,
and a lifecycle in which every new source needs an engineer before it can even be
*tested* is the "if every new source is an engineering project, the platform has
failed" condition, expressed as a lock.

`RunMode.ACCEPTANCE` breaks it, narrowly:

- It admits `AWAITING_EVIDENCE` and **never** `SCAFFOLD` — there is no
  implementation for an acceptance run to gather evidence about.
- It skips the **config** key, because turning that key is the *outcome* of the
  acceptance run, not its precondition.
- It does **not** skip the code key; it widens what the code key accepts.
- It is recorded on the run, so evidence is self-labelling and an acceptance run
  can never be mistaken for production ingest after the fact.

The readiness check reports it explicitly ("this is not a production run and does
not imply either ADR-0030 key is turned") so a green pre-flight on an acceptance
run is not misread as an open lock.

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

### D. Break the acceptance deadlock with an environment-gated bypass

*(Considered 2026-07-20, #743.)* Let `AWAITING_EVIDENCE` satisfy the code key
whenever the environment is non-production. Rejected: it keys a safety property
on deploy config rather than declared intent, nothing marks the resulting run as
a rehearsal, and #712 is open precisely because `ENVIRONMENT` is unset in places
— so the guard could be silently wrong in the direction that opens the lock.
`RunMode.ACCEPTANCE` puts the intent in the request and on the run record.

### E. Flip the code key first and treat the acceptance run as ratification

Ship `live_ready = True` for a built provider, then run the acceptance loop.
Rejected as the general answer: it is indistinguishable, at the moment of the
flip, from flipping on confidence — the thing the whole lock exists to stop —
and it leaves the deadlock in place for the next locked provider, so the cost of
the Nth source never falls.

## Consequences

**Positive:**

- Scaffolds are safe to commit and reference; the two-key lock makes an
  accidental live run structurally impossible.
- The code-readiness boundary is explicit in code (`AcquisitionReadiness`) and
  the live decision is explicit in config (`enabled`), with separate owners.
  The three-state code key also distinguishes "needs an engineer" from "needs an
  acceptance run", so the panel stops sending operators to build what exists.
- Template misconfiguration fails in CI, not against a live third party.
- One jurisdiction can carry mixed compliance tiers per authority.
- Live-enablement is an auditable operator workflow with evidence under
  version control.

- A provider can earn its own first key: `RunMode.ACCEPTANCE` lets an operator
  produce the evidence the lock asks for, so onboarding the Nth source does not
  require an engineer (§6).

**Negative:**

- Two keys mean two places to change when genuinely going live; an
  operator who flips only `enabled` on a still-scaffold provider gets a
  `ProviderNotLiveReadyError` rather than a run. This is intentional but is
  a footgun without the runbook.
- `extra="forbid"` makes spec evolution slightly stricter: adding a field
  to a template requires adding it to the spec model first.
- **`RunMode.ACCEPTANCE` reaches a live portal with the config key waived.**
  That is a deliberate hole in an otherwise fail-closed lock, and it is the
  riskiest thing in this ADR. It is bounded three ways: the code key still
  applies (a `SCAFFOLD` provider is refused in every mode), the waiver is
  limited to `AWAITING_EVIDENCE` — so an operator's explicit `enabled: false`
  kill switch still stops a `LIVE` provider — and the mode cannot be attached to
  a schedule, so a rehearsal cannot become an unattended crawl. Those bounds are
  what the mode's safety rests on; weakening any of them re-opens the hole.
- A three-state code key is more to hold in mind than a boolean, and the boolean
  survives as a derived projection, so two spellings of the same fact now exist.
  `provider_readiness()` is the only correct reader; setting `live_ready`
  directly on a provider that declares `readiness` is a silent no-op.

## References

- [`platform-control/src/acquisition_core/providers.py`](../../platform-control/src/acquisition_core/providers.py)
  — protocol, `AcquisitionReadiness`, `provider_readiness()`,
  `ensure_launchable()` / `require_live_ready()`.
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
