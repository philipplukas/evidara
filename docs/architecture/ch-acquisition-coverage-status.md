# CH acquisition coverage status and roadmap

Honest snapshot of what Evidara actually acquires for Switzerland, what is
plumbed but held disabled, and what is not built. Read alongside
[ADR-0030: Acquisition provider enablement lifecycle](../adr/0030-acquisition-provider-enablement-lifecycle.md),
which defines the two-key lock (provider readiness AND `template.enabled`)
and the acceptance-run → evidence → flip-live workflow that governs every
transition below.

> **Amended 2026-09-03.** Rebuilt from the code after drifting past #797
> (LexFind provider), #815 (LexFind promoted to `LIVE`), #817/#818
> (whole-canton enumeration), #819 (coverage ledger) and #735/#589
> (`gemeinde_http` promoted to `LIVE`). The previous revision named no
> LexFind provider at all, asserted that `canton_http` was "not present on
> `main`", and listed binary/PDF acquisition as NOT BUILT — all three were
> false by the time it was read. Verify against the code, not against this
> file (AGENTS.md).
>
> **Amended 2026-07-20 (#743).** The code key is three-state
> (`scaffold` / `awaiting_evidence` / `live`), not a boolean. "Scaffold" below
> now means specifically `readiness = scaffold` — `start_run` is not
> implemented. A provider that is built but has no acceptance evidence is
> `awaiting_evidence`, and an operator can dispatch a `mode=acceptance` run to
> produce that evidence without an engineer.

The status labels map directly onto the two keys:

- **LIVE** — provider readiness `live` and at least one template
  `enabled: true`; acquisition runs today.
- **CODE-LIVE, CONFIG-SHUT** — provider readiness `live` (acceptance
  evidence exists and was accepted) but every template still ships
  `enabled: false`. The operator's key has not been turned, so nothing
  acquires. **This is not the same claim as LIVE**, and the distinction is
  the point of the two-key lock.
- **PLUMBED-BUT-DISABLED** — the provider and templates exist and parse,
  but the code key is `awaiting_evidence` or `scaffold`, so no production
  run can fire.
- **NOT BUILT** — no provider or template yet; design or code work
  remains.

## Provider readiness as declared in code

Every provider registered by
[`provider_registry_factory.build_provider_registry`](../../platform-control/src/platform_control/services/provider_registry_factory.py),
with the `readiness` class attribute read from each provider module. This
table is a **snapshot**: the runtime source of truth is
`POST /v1/sources/blueprint-preview`, which returns `acquisition_readiness`,
`enabled` and `launchable` for a given overlay + template
(`platform-control/src/platform_control/routers/sources.py:93-102`).

| Provider | `readiness` | Declared at |
|---|---|---|
| `firecrawl` | `live` | `services/firecrawl_provider.py:22` |
| `deterministic_http` | `live` | `services/deterministic_http_provider.py:27` |
| `fedlex_sparql` | `live` | `services/fedlex_sparql_provider.py:123` |
| `ris_ogd` | `live` | `services/ris_ogd_provider.py:119` |
| `eur_lex_sparql` | `live` | `services/eur_lex_sparql_provider.py:88` |
| `legifrance` | `scaffold` | `services/legifrance_provider.py:64` |
| `bundesland_http` | `live` | `services/bundesland_http_provider.py:32` |
| `regione_http` | `live` | `services/regione_http_provider.py:29` |
| `ch_court_decisions` | `awaiting_evidence` | `services/ch_court_decisions_provider.py:234` |
| `canton_http` | `scaffold` | `services/canton_http_provider.py:48` |
| `lexfind_api` | `live` | `services/lexfind_api_provider.py:354` |
| `gemeinde_http` | `live` | `services/gemeinde_http_provider.py:304` |
| `cassette` | `live` | `services/cassette_provider.py:50` (fixture replay, SHADOW mode only) |

The three states are defined in
[`acquisition_core/providers.py:92-118`](../../platform-control/src/acquisition_core/providers.py).

## LIVE — federal legislation (Fedlex)

Swiss federal legislation is acquired today through the `fedlex_sparql`
provider (`readiness = LIVE`) resolving ELI work URIs to expression
manifestations via the Fedlex SPARQL endpoint, plus a `deterministic_http`
fallback over `fedlex.admin.ch`. Enabled templates in the `ch` overlay of
[`source_blueprints.yaml`](../../platform-control/src/platform_control/hierarchies/source_blueprints.yaml)
are `deterministic_http_fedlex_legislation`, `fedlex_sparql_constitution_de`,
`fedlex_sparql_vwvg_de`, `fedlex_sparql_federal_law_batch_de` and
`fedlex_sparql_federal_codes_de` (BV, VwVG, ZGB, OR, SchKG, BGG,
KVG, AHVG, RPG, USG, URG). A sixth template,
`fedlex_sparql_tierschutz_de` (TSchG SR 455 / TSchV SR 455.1), ships
`enabled: false` on purpose: ADR-0030 turns the config key per template
after *that* template's own acceptance evidence, and an inherited default
is not evidence.

Compliance runs under the open-data tier
(`cp_ch_fedlex_open_data`) bound to `jur_ch_federal`. The
[`scripts/ch-fedlex-fast-loop.sh`](../../scripts/ch-fedlex-fast-loop.sh)
acceptance harness exercises this path end-to-end (capture → DI lifecycle
→ content gates). Background on the temporal/ELI model:
[CH Fedlex SPARQL temporal architecture](ch-fedlex-sparql-temporal-architecture.md).

## CODE-LIVE, CONFIG-SHUT — cantonal legislation via LexFind (#731)

`lexfind_api` is the cantonal rung. LexFind (`www.lexfind.ch`, a project of
the *Schweizerische Staatsschreiberkonferenz*) exposes an unauthenticated
JSON API over the same texts of law the cantons publish themselves — 26
cantons plus Bund, 28 entities, behind one contract. One provider covers
the whole rung, which is why it was prioritised: #628 measures the cost of
the Nth source, and 28 jurisdictions behind one homogeneous contract is the
cheapest available test of whether that cost falls.

**Provenance is proved, not asserted.** #716 verified the mirrored file is
md5-identical to the canton's own (`461c614535cb7b5aa33175904f7d3229` for
the ZH Hundegesetz, Wayback copy of `notes.zh.ch` vs. LexFind `/tol/22871/de`),
and every record carries `original_url` back to the canton's own page, so the
canonical citation survives the mirror
(`services/lexfind_api_provider.py:16-27`).

**It models repeal separately from consolidation.**
`version_inactive_since` is its own field, so a repealed act cannot be
masqueraded as in force by an open-ended newest consolidation — the #661
trap that Fedlex's `dateEndApplicability` falls into
(`services/lexfind_api_provider.py:104-113`).

**The code key is turned; the operator's key is not.**
`readiness = AcquisitionReadiness.LIVE` since 2026-07-28
(`services/lexfind_api_provider.py:354`, promoted in #815), on three
ADR-0030 acceptance bundles, all `execution_mode: live`, all
`skipped_gates: []`:

| Bundle | Canton | Captured |
|---|---|---|
| [`2026-07-22-ch-canton-zh-lexfind-acceptance-v3`](../runbooks/evidence/2026-07-22-ch-canton-zh-lexfind-acceptance-v3/) | ZH | 4 PDFs (554.1 / 554.11 / 554.5 / 554.51), 4/4 through DI, 9 search hits |
| [`2026-07-28-ch-canton-be-lexfind-acceptance`](../runbooks/evidence/2026-07-28-ch-canton-be-lexfind-acceptance/) | BE | 2 PDFs (916.31 Hundegesetz, 916.812 THV), 2/2 through DI, 1 hit |
| [`2026-07-28-ch-canton-bs-lexfind-acceptance`](../runbooks/evidence/2026-07-28-ch-canton-bs-lexfind-acceptance/) | BS | 5 PDFs (365.100 / .110 / .101 + two communal), 5/5 through DI, 7 hits |

**Every one of those runs was `environment: compose-local`** (the
`environment` field of each bundle's `summary.json`). No LexFind template is
enabled in any environment: `lexfind_api_zh_tierschutz`,
`lexfind_api_be_hunde`, `lexfind_api_bs_hunde` and `lexfind_api_zh_full` all
ship `enabled: false`. **There is therefore no cantonal Swiss law in dev,
staging or production.** A LIVE code key asserts that the code works and was
evidenced once; it asserts nothing about a deployed corpus.

**Coverage is a separate claim from onboarding.** The three search-scoped
templates each enumerate one systematic-number branch (`554` scoped to
entity 26 returns the whole ZH animal-protection branch in one request) —
that is ADR-0033's dog-question slice, not the canton's corpus. #818 added
`lexfind_api_zh_full`, which enumerates a whole entity by the union over
systematic-number digits 0-9 (measured live 2026-07-28: 1,377 deduplicated
against a published `entities/extended` total of 1,377, in ~40 requests) and
reports `observed / expected / gap` rather than reporting success for
whatever it found. It runs with `active_only: False` on purpose — ZH's 1,377
includes 433 repealed acts, and point-in-time questions need them. That
template is also `enabled: false`.

Do not read "3 cantons onboarded" as "3 cantons held", and do not read
"one provider, 26 cantons" as "26 cantons done".

**Where the numbers live.** #819 added
`GET /v1/acquisition-coverage` (`platform_control/routers/coverage.py:26`),
the platform-control half of the ADR-0042 §4 split: per jurisdiction,
`expected → discovered → acquired → processed`, with gaps suppressed on a
truncated (sampled) run so a deliberately capped run cannot read as a
coverage failure. It publishes no percentage, ratio or score.

## CODE-LIVE, CONFIG-SHUT — communal legislation, Stadt Zürich (#584)

The municipal layer is where the ADR-0033 acceptance test actually lives
("can the city ban a certain thing for dogs, year-round?" — the act being
challenged is a *communal* ordinance). 2,110 `jur_ch_gemeinde_*`
jurisdictions were seeded with no authority, no template and no provider:
modelled and unreachable. #584 landed the first reachable commune —
deliberately **one** city, not 2,110.

**What the City of Zürich publishes** (verified 2026-07-14): the Amtliche
Sammlung is a systematic collection with stable, AS-number-shaped URLs
(AS 554.510 → `…/amtliche-sammlung/5/554/510.html`). robots.txt permits
these paths. That URL is a **metadata landing page, not the law** — it
carries the AS number, title, Beschlussdatum, Inkrafttreten,
**Ausserkrafttreten** and a version history in an embedded JSON blob, plus
a link to the operative text. The operative text is a **PDF**; there is no
HTML manifestation. The metadata is valuable on its own: `Ausserkrafttreten`
is exactly the repeal/until date ADR-0033 records the corpus as lacking.

**The two blockers this section used to list are both gone.** The previous
revision said `ProviderResource.body` is typed `str` so the interface cannot
carry bytes, and that `document-intelligence` has no PDF path. Neither is
true on `main`:

1. `ProviderResource` carries `body_bytes: bytes | None` alongside
   `body: str | None`, exactly one of which is set
   (`acquisition_core/providers.py:25-40`, #590 / ADR-0037). The provider
   emits the PDF as bytes and never decodes it
   (`services/gemeinde_http_provider.py:34-41`).
2. `document-intelligence/src/document_intelligence/normalize/` ships
   `pdf.py` and `marginalia.py` beside `html.py` and `xml.py`. The
   right-margin *Randtitel* splice that made naive extraction untrustworthy
   — "die Führung des **Organisation** Hundeverzeichnisses" — is fixed by
   partitioning on shared line-start edges rather than x-projection gutters,
   and is asserted against the real AS 554.510 PDF in
   `document-intelligence/tests/test_marginalia.py` (#650 / ADR-0041).

`gemeinde_http` is therefore `readiness = LIVE`
(`services/gemeinde_http_provider.py:304`), on acceptance evidence captured
against live Zürich AS 554.510 on 2026-07-20
([`2026-07-20-ch-gemeinde-zuerich-acceptance.md`](../runbooks/evidence/2026-07-20-ch-gemeinde-zuerich-acceptance.md)) —
also `environment: compose-local`. The single template
`gemeinde_http_zh_stadt_hundevorschriften` ships `enabled: false`, so no
communal law is acquired in any environment.

The provider still **refuses** on an unrecognised manifestation rather than
emitting the metadata landing page as a stand-in for the ordinance —
indexing a metadata stub as if it were the law is the "demo that lies
convincingly" failure ADR-0033 exists to prevent.

**How far this generalises: less than it looks.** The BFS → host allow-list
lives in `communal_portals.yaml`, so registering a commune's *host* is a
config edit. The **parser is not** config: it reads Stadt Zürich's Amtliche
Sammlung schema specifically (the `ASZ` field id, the `rechtstexte` link
field, `erlassdatum` / `inkrafttretendatum` / `ausserkrafttretendatum`). A
commune with a different page shape yields no manifestation link and the run
fails — correctly, but the remedy is a parser, not a config edit
(`services/gemeinde_http_provider.py:81-90`). That misreading is what sent
issue #736 looking for a registration mechanism when the binding constraint
is per-portal parsing.

## PLUMBED-BUT-DISABLED — awaiting evidence or engineering

### Federal and cantonal court decisions — `ch_court_decisions` (#530, #531)

The provider is **built but unproven**
(`readiness = AWAITING_EVIDENCE`, `services/ch_court_decisions_provider.py:234`) —
implemented and unit-tested against captured fixtures, awaiting an
acceptance run, **not** a scaffold (#743).

Five templates ship `enabled: false`: `ch_court_decisions_bger` and
`ch_court_decisions_bvger` (federal, placeholder seed URLs), plus
`ch_court_decisions_zh`, `_be` and `_bs`. Cantonal rulings are aggregated on
`entscheidsuche.ch`, which has no per-canton host, so those templates carry
an explicit lowercase `court` hint that is passed through to the resource
metadata (`services/ch_court_decisions_provider.py:7-14`).

Compliance is pre-declared: `cp_ch_court_decisions` is a
public-official-tier policy (robots strict, ~20 rpm, 2 concurrent, 365-day
retention) intended to bind at the **authority** level (`auth_bger` /
`auth_bvger`) so court runs are stricter than Fedlex legislation while both
sit under `jur_ch_federal` — see the authority-over-jurisdiction resolution
in ADR-0030 §4. Live-enablement requires real discovery URLs and a `pass`
verdict from the [`scripts/ch-bger-fast-loop.sh`](../../scripts/ch-bger-fast-loop.sh)
court harness before either key flips.

### Cantonal portal legislation — `canton_http` (superseded by LexFind)

`canton_http` **is** on `main`
(`services/canton_http_provider.py`), following the ADR-0025
`PortalHttpProviderBase` config-driven multi-tenant pattern, with templates
`canton_http_zh`, `canton_http_be` and `canton_http_bs`, all
`enabled: false`. It is `readiness = SCAFFOLD`
(`services/canton_http_provider.py:48`) — and deliberately so: although
`start_run` is inherited and real, #716 measured that the ZH-Lex
`erlass-*.html` pages are metadata-only (`§ = 0` on all 18 sampled,
1879→2026) and their only text link points at `www.notes.zh.ch`, a host that
refuses TCP on 443 and 80. The remedy is engineering, not an operator run,
so `SCAFFOLD` correctly refuses runs of every mode.

`lexfind_api` is the answer to this scaffold. Treat `canton_http` as
dormant, not as the intended home for cantonal statute coverage.

### Cantonal legislation via Fedlex — REMOVED, the premise was false (#716)

`fedlex_sparql` once carried a `canton_discovery` mode, with templates
`fedlex_sparql_canton_zh` / `_be` / `_bs`, which discovered works via a
`jolux:CantonOfOrigin` predicate. **That predicate never existed, and Fedlex
publishes no cantonal law.** The mode and the three templates were removed
in #716 rather than left dormant: `fedlex_sparql` is `readiness = LIVE`, so
the `enabled: false` default was the only thing between an operator and a run
that could only ever capture zero documents.

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
systematic collection.

## NOT BUILT

- **Cantonal coverage beyond ZH/BE/BS templates** — `lexfind_api` reaches
  all 28 LexFind entities, but only ZH, BE and BS have templates, and only
  ZH has a whole-entity enumeration template. The other 23 cantons have no
  template at all.
- **National communal coverage** — communal law lives on ~2,000
  independent municipal sites with no common schema. Only Zürich (BFS 261)
  is allow-listed, and the per-portal parser (not the host allow-list) is
  the binding constraint. A 2026-07-22 survey of all 2,110 communes found
  platform clustering covers only ~5% of the registry. This is likely the
  hardest acquisition problem in the project.
- **A French provider** — `legifrance` is `readiness = SCAFFOLD`
  (`services/legifrance_provider.py:64`). Not CH, listed here only because
  the readiness table above shows it.
- **CI-gated CH e2e (#533)** — an automated, CI-gated end-to-end check for
  the CH streams is pending. Today the fast-loop harnesses are run
  on-demand by an operator, not enforced as a required CI status check.

## Roadmap and dependencies

Ordered by dependency. Every live transition depends on an **operator
acceptance run** producing a `pass` verdict and evidence under
[`docs/runbooks/evidence/`](../runbooks/evidence/README.md); this is the
gate that code alone cannot satisfy (ADR-0030 §5).

| # | Step | Code key | Remaining gate |
|---|------|-----------|-----------------|
| 1 | Federal legislation (Fedlex) | `live` | Done — both keys open, acquires today |
| 2 | Cantonal legislation via LexFind (#731) | `live` since #815 | Operator flips `enabled: true` on the ZH/BE/BS templates from the admin panel with the bundles linked; no environment beyond compose-local holds cantonal law until then |
| 3 | Whole-canton coverage (#816/#818) | `live` (same provider) | Enable `lexfind_api_zh_full`, then add a `_full` template per canton; the coverage ledger (`GET /v1/acquisition-coverage`) is what makes the claim checkable |
| 4 | Communal legislation — Stadt Zürich (#584) | `live` since #735 | Operator flips `enabled: true` on `gemeinde_http_zh_stadt_hundevorschriften` |
| 5 | Federal court decisions (#530) | `awaiting_evidence` | Real discovery URLs + a `pass` acceptance run → flip both keys |
| 6 | Cantonal court decisions (#531) | `awaiting_evidence` (same provider) | Templates exist for ZH/BE/BS against `entscheidsuche.ch`; needs the same acceptance run |
| 7 | CI-gated CH e2e (#533) | n/a | Wire the fast-loops as a required CI status check |
| 8 | Remaining 23 cantons | `live` (same provider) | Per-canton templates; the provider is unchanged, the cost is config + evidence |
| 9 | Full communal coverage (#736) | `live` for ZH's portal shape only | A parser per portal shape — ~2,000 municipal sites, a programme, not a step |
| — | Cantonal portal scraping (`canton_http`) | `scaffold` | Superseded by LexFind. Do not plan against it |

See the
[country rollout & drift-prevention backlog](../runbooks/country-rollout-drift-prevention-backlog.md)
for the cross-country framing this CH view sits inside.
