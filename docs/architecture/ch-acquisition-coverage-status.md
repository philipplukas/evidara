# CH acquisition coverage status and roadmap

Honest snapshot of what Evidara actually acquires for Switzerland, what is
plumbed but held disabled, and what is not built. Read alongside
[ADR-0030: Acquisition provider enablement lifecycle](../adr/0030-acquisition-provider-enablement-lifecycle.md),
which defines the two-key lock (`provider.live_ready` AND `template.enabled`)
and the acceptance-run → evidence → flip-live workflow that governs every
transition below.

The status labels map directly onto the two keys:

- **LIVE** — provider `live_ready: true` and at least one template
  `enabled: true`; acquisition runs today.
- **PLUMBED-BUT-DISABLED** — the provider and templates exist and parse,
  but one or both keys are off, so no run can fire. Awaiting operator
  acceptance evidence (or, in one case, a provider that lives on another
  branch).
- **NOT BUILT** — no provider or template yet; design or code work
  remains.

## LIVE — federal legislation (Fedlex)

Swiss federal legislation is acquired today through the `fedlex_sparql`
provider (`live_ready: true`) resolving ELI work URIs to expression
manifestations via the Fedlex SPARQL endpoint, plus a `deterministic_http`
fallback over `fedlex.admin.ch`. Enabled templates in the `ch` overlay of
[`source_blueprints.yaml`](../../platform-control/src/platform_control/hierarchies/source_blueprints.yaml)
include `fedlex_sparql_federal_codes_de` (BV, VwVG, ZGB, OR, SchKG, BGG,
KVG, AHVG, RPG, USG, URG). Compliance runs under the open-data tier
(`cp_ch_fedlex_open_data`) bound to `jur_ch_federal`. The
[`scripts/ch-fedlex-fast-loop.sh`](../../scripts/ch-fedlex-fast-loop.sh)
acceptance harness exercises this path end-to-end (capture → DI lifecycle
→ content gates). Background on the temporal/ELI model:
[CH Fedlex SPARQL temporal architecture](ch-fedlex-sparql-temporal-architecture.md).

## PLUMBED-BUT-DISABLED — awaiting live-enablement

These paths are fully plumbed (spec models, templates, and — except where
noted — a `live_ready` provider) but ship with at least one key off. Each
needs an operator acceptance run whose evidence justifies flipping the
remaining key(s), per ADR-0030 §5.

### Federal court decisions — BGer / BVGer (#530)

The `ch_court_decisions` provider is a **scaffold** (`live_ready: false`).
Templates `ch_court_decisions_bger` and `ch_court_decisions_bvger` ship
`enabled: false` with placeholder seed URLs. Compliance is pre-declared:
`cp_ch_court_decisions` is a public-official-tier policy (robots strict,
~10–20 rpm, 365-day retention) intended to bind at the **authority** level
(`auth_bger` / `auth_bvger`) so court runs are stricter than Fedlex
legislation while both sit under `jur_ch_federal` — see the
authority-over-jurisdiction resolution in ADR-0030 §4. Live-enablement
requires implementing the provider, setting real discovery URLs, and a
`pass` verdict from the `scripts/ch-bger-fast-loop.sh` court harness (which
lands alongside the provider) before both keys flip.

### Cantonal legislation via Fedlex — REMOVED, the premise was false (#716)

`fedlex_sparql` once carried a `canton_discovery` mode, with templates
`fedlex_sparql_canton_zh` / `_be` / `_bs`, which discovered works via a
`jolux:CantonOfOrigin` predicate. **That predicate never existed, and Fedlex
publishes no cantonal law.** The mode and the three templates were removed in
#716 rather than left dormant: `fedlex_sparql` is `live_ready: true`, so the
`enabled: false` default was the only thing between an operator and a run that
could only ever capture zero documents.

Measured against `https://fedlex.data.admin.ch/sparqlendpoint` on 2026-07-19:

| Probe | Result |
|---|---|
| `SELECT (COUNT(*)) WHERE { ?s ?p ?o }` | 56,238,852 triples — the endpoint is live, so the negatives below are real |
| `SELECT DISTINCT ?p` | 426 predicates, **zero** containing `anton` (covers `Canton` and `Kanton`) |
| `ASK` on 6 spellings (`CantonOfOrigin`, `cantonOfOrigin`, `canton`, `Canton`, `applicableCanton`, `cantonalAuthority`) | all `false` |
| `GET /vocabulary/canton/ZH` | **404** (control: `/vocabulary/legal-institution/3525` → 200) |
| `SELECT DISTINCT ?t WHERE { ?s a ?t }` | 133 classes, none cantonal; `jolux:Country` exists — Fedlex models *country*, not canton |
| ELI collection segments | only `fga` (BBl), `oc` (AS), `cc` (SR) — all federal |

**Correcting the previous claim in this section.** It said cantonal Fedlex
covered "concordats and inter-cantonal agreements **of origin ZH/BE/BS**". The
concordats are real — e.g. `eli/oc/1980/1631_1631_1631`, "Konkordat über die
Vollstreckung von Zivilurteilen" — but the "of origin ZH/BE/BS" part is not
expressible. Every predicate on such a work is pure AS-collection metadata
(`memorialName`, `memorialYear`, `identifier`, `memorialPage`, `title`,
`language`, …) with **no cantonal attribution of any kind**. Fedlex models a
concordat as a federal-gazette publication. So canton discovery could not have
worked even with a corrected predicate name — there is nothing to filter on.

Fedlex is the Federal Chancellery platform for Bundesrecht (BBl / AS / SR);
cantonal law is out of scope by design, and each canton runs its own
systematic collection. Cantonal coverage therefore requires a **per-canton
provider against the canton's own portal**, not a mode on `fedlex_sparql`.
See the `canton_http` section below.

### Cantonal portal legislation — `canton_http` provider

A `canton_http` portal provider (following the ADR-0025
`PortalHttpProviderBase` config-driven multi-tenant pattern) is being
developed on a separate branch and is **not present on `main`**. Until it
merges, cantonal portal legislation — the bulk of cantonal law noted above
— has neither a provider nor templates here. Treat this as the intended
home for real per-canton statute coverage, distinct from the Fedlex
concordat slice.

### Communal legislation — `gemeinde_http` provider (#584)

The municipal layer is where the ADR-0033 acceptance test actually lives
("can the city ban a certain thing for dogs, year-round?" — the act being
challenged is a *communal* ordinance). 2,110 `jur_ch_gemeinde_*`
jurisdictions were seeded with **no authority, no template and no
provider**: modelled and unreachable. #584 lands the first reachable
commune — deliberately **one** city, not 2,110.

**What the City of Zürich publishes** (verified 2026-07-14): the Amtliche
Sammlung is a systematic collection with stable, AS-number-shaped URLs
(AS 554.510 → `…/amtliche-sammlung/5/554/510.html`). robots.txt permits
these paths. But that URL is a **metadata landing page, not the law** — it
carries the AS number, title, Beschlussdatum, Inkrafttreten,
**Ausserkrafttreten** and a version history in an embedded JSON blob, plus
a link to the operative text. **The operative text is a PDF. There is no
HTML manifestation.**

Note the metadata is genuinely valuable on its own: `Ausserkrafttreten` is
exactly the repeal/until date ADR-0033 records the corpus as lacking. The
provider parses it (and is unit-tested against a verbatim capture of the
live page).

**Why both keys stay shut.** Two independent, structural blockers, neither
fixable inside the provider:

1. `acquisition_core.ProviderResource.body` is typed `str` — the
   acquisition interface cannot carry binary bytes at all.
2. `document-intelligence` has no PDF path: `normalize/` ships `html.py`
   and `xml.py` only, and both the legacy and `docling` backends take
   `artifact_text: str`. An `application/pdf` artifact falls through to
   `normalize_plain_text_document`, which would normalize raw PDF binary.

Naive text extraction is **not** a shortcut: the AS PDFs carry marginal
headings (*Randtitel*) that `pdftotext` splices mid-sentence — "die Führung
des **Organisation** Hundeverzeichnisses" — silently corrupting the legal
text. Municipal law needs a layout-aware PDF pipeline.

The provider therefore **refuses** on a PDF-only manifestation rather than
emitting the metadata landing page as a stand-in for the ordinance —
indexing a metadata stub as if it were the law is the "demo that lies
convincingly" failure ADR-0033 exists to prevent. A commune that published
HTML law would acquire normally through the same code path.

**Unblocked by:** a binary-artifact path through `ProviderResource` +
artifact store, and a layout-aware PDF normaliser in
document-intelligence. Neither belongs in a provider PR.

## NOT BUILT

- **Cantonal court decisions** — no provider or templates. Federal court
  decisions (#530) come first; cantonal case law is a later tier.
- **Binary (PDF) artifact acquisition** — the whole acquisition +
  normalisation path is text-only end to end (see the `gemeinde_http`
  section above). This is the single blocker on the municipal layer, and
  Swiss communal law is overwhelmingly PDF.
- **National communal coverage** — communal law lives on ~2,000
  independent municipal sites with no API and no common schema. Only
  Zürich (BFS 261) is allow-listed. This is likely the hardest acquisition
  problem in the project and is explicitly out of scope for the vertical
  slice.
- **Full per-canton portal coverage** — beyond the ZH/BE/BS Fedlex
  concordat slice, no cantonal portal statutes are covered. Even once
  `canton_http` lands, the first targets are a small allow-list of cantons
  (ZH/BE/BS), not all 26.
- **CI-gated CH e2e (#533)** — an automated, CI-gated end-to-end check for
  the CH streams is pending. Today the fast-loop harnesses are run
  on-demand by an operator, not enforced as a required CI status check.

## Roadmap and dependencies

Ordered by dependency. Every live transition depends on an **operator
acceptance run** producing a `pass` verdict and evidence under
[`docs/runbooks/evidence/`](../runbooks/evidence/README.md); this is the
gate that code alone cannot satisfy (ADR-0030 §5).

| # | Step | Depends on | Gate to go LIVE |
|---|------|-----------|-----------------|
| 1 | Federal legislation (Fedlex) | — | Done — LIVE |
| 2 | Federal court decisions (#530) | Implement `ch_court_decisions` (`live_ready`) + real discovery URLs | `ch-bger-fast-loop.sh` `pass` → flip both keys |
| 3 | Cantonal legislation via Fedlex (#531) | Provider already live | Cantonal acceptance run → `enabled: true` on canton templates |
| 4 | Cantonal portal legislation | `canton_http` provider merges to `main` | Per-canton acceptance run → enable ZH/BE/BS portal templates |
| 5 | CI-gated CH e2e (#533) | Steps 2–3 live | Wire fast-loops as a required CI status check |
| 6 | Cantonal court decisions | Steps 2 + 4 patterns | New provider + acceptance run |
| 7 | Full per-canton portal coverage | Step 4 | Extend `canton_http` allow-list beyond ZH/BE/BS |
| 8 | Communal legislation — Stadt Zürich (#584) | **Binary-artifact path + layout-aware PDF normaliser** — the provider and template are landed and inert until then | Acceptance run on AS 554.510 → flip both keys |
| 9 | Full communal coverage | Step 8 | ~2,000 municipal sites — a programme, not a step |

See the
[country rollout & drift-prevention backlog](../runbooks/country-rollout-drift-prevention-backlog.md)
for the cross-country framing this CH view sits inside.
