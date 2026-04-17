# ADR-0025: Portal HTTP provider strategy (config-driven multi-tenant)

Status: Accepted
Date: 2026-04-17
Deciders: Contracts / Platform
Related: ADR-0024 (CI runner strategy), ADR-0022 (agentic CLI workflow)

## Context

Sub-federal legal content is published on per-jurisdiction HTML portals:

- **Germany:** 16 Bundesländer, each with a distinct portal
  (`gesetze-bayern.de`, `recht.nrw.de`, `landesrecht-bw.de`,
  `gesetze.berlin.de`, `landesrecht-hamburg.de`, and 11 others).
- **Italy:** 20 regioni, each with a distinct portal
  (`normelombardia.consiglio.regione.lombardia.it`,
  `consiglio.regione.lazio.it`, and 18 others).
- **Switzerland:** cantonal portals (26 cantons) when we extend beyond
  Fedlex.
- **France:** régional portals when we extend beyond Légifrance.

The first sub-federal adapters were shipped as scaffolds in an earlier
commit on branch `claude/plan-next-steps-OANlO`
(`BundeslandHttpProvider`, `RegioneHttpProvider`), each with an inline
dict of supported codes raising `NotImplementedError` on every
`start_run`.

We now need to decide how the live adapters are organized before
rolling out Bayern (`DE-BY`) and Lombardia (`IT-25`) as acceptance
targets.

## Decision

Adopt a **config-driven multi-tenant** pattern per jurisdiction tier:

- One provider class per jurisdiction tier (DE Bundesland, IT regione,
  CH canton when we add it, FR région when we add it), implemented as
  a thin subclass of a shared `PortalHttpProviderBase`.
- The base class owns the acquisition flow: fetch seed URLs → extract
  title → emit `ProviderResource`.
- Each subclass carries a **supported-portals allow-list**: ISO 3166-2
  code → portal host. The allow-list is consulted at run-time to
  reject seed URLs that don't match the declared jurisdiction.
- Per-portal configuration (seed URLs, timeout, max content bytes)
  lives in the blueprint template under `source_blueprints.yaml`, not
  in code.

Subclasses stay < 20 lines each: provider name, subdivision spec key,
country scope, supported-portals map. Any portal that needs genuinely
custom logic (JavaScript rendering, auth, bespoke pagination) escapes
this pattern by shipping its own dedicated provider class.

## Alternatives considered

### A. Multi-tenant with inline adapter dict (status quo scaffold)

A single class per tier with a `dict[code, adapter_instance]` holding
per-portal adapter objects. Live implementation per state lives inside
the switch.

Rejected: each new state becomes a class-level code change. The class
would grow long and hard to test in isolation; per-state mocking gets
tangled with the others.

### B. Per-portal provider (one class per state)

16 DE Bundesland provider classes + 20 IT regione classes = 36 Python
files, each with their own tests. Full isolation, but:

- Duplicates the shared acquisition flow 36 times.
- Registration in `provider_registry_factory.py` becomes 36 `register`
  calls.
- The enum (`AcquisitionProvider`) grows to 36+ values.
- Each new jurisdiction requires a PR that touches code, even when
  the portal shape is identical to an existing one.

Rejected: too much scaffolding cost up front. The escape hatch (custom
class for a specifically weird portal) is still available.

### C. Fully declarative generic scraper

One class that accepts URL templates + CSS/XPath selectors from
template config, no Python per portal. Maximum flexibility.

Rejected: Evidara's portals are mostly simple enough for the generic
flow, but the selector-config model doesn't handle portals that need
JavaScript rendering or auth. A generic scraper would be over-
abstracted for the easy cases and insufficient for the hard cases.

## Consequences

**Positive:**

- New states land as one-line entries in the `supported_portals` dict
  plus a blueprint template. No code growth per state.
- Base-class tests cover the acquisition flow; per-state tests only
  need to verify the supported-portals entry.
- Host allow-list is enforced uniformly — no portal can be pointed at
  an attacker-controlled domain even if the template is malicious.

**Negative:**

- Portals with truly custom needs (ReCaptcha, cookie walls,
  JavaScript-rendered content) cannot use this pattern. They must
  ship a dedicated provider class and a new enum entry.
- `ProviderConfigurationError` at run time is the surface for
  "operator misconfigured the template" — blueprint parsing doesn't
  catch it. A schema for `acquisition_spec` per provider would tighten
  this; tracked as T1-follow-up in the drift-prevention backlog.

## Implementation

Shipped in the commit that lands this ADR:

- `platform_control/services/portal_http_provider_base.py` — shared
  base with acquisition flow, title extraction, and host allow-list.
- `platform_control/services/bundesland_http_provider.py` — 15-line
  subclass with 5 supported DE portals (`DE-BY`, `DE-NW`, `DE-BW`,
  `DE-BE`, `DE-HH`).
- `platform_control/services/regione_http_provider.py` — 12-line
  subclass with 4 supported IT portals (`IT-25`, `IT-62`, `IT-52`,
  `IT-21`).
- 12 new unit tests covering end-to-end flow, host allow-list, code
  validation, title extraction, and cross-country rejection.
- Both providers flip `live_ready = True`. Blueprint templates
  (`bundesland_http_bayern`, `regione_http_lombardia`) stay
  `enabled: false` until operator acceptance-run evidence lands.

## References

- `docs/runbooks/country-rollout-drift-prevention-backlog.md` §T2.1
  (multi-tenant vs per-portal decision) + §T4.2 + §T4.3.
- `docs/architecture/vocabulary-standards.md` §Single-source-of-truth
  rule (provider tokens live on subdivisions.json).
- `platform_control/services/fedlex_sparql_provider.py` and
  `platform_control/services/eur_lex_sparql_provider.py` as the
  SPARQL parallel (one class per source family; ontology-driven
  rather than portal-driven).
