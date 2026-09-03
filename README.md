# Evidara

A data platform for law. It acquires primary legal sources **directly from the bodies that issue
them**, turns the captured bytes into canonical structured documents, and serves them for search —
with every step of that path gated on evidence that it actually worked, and with full provenance
back to the issuing source kept on every record.

Coverage today spans Swiss federal and cantonal law, Austria, Germany, Italy, France and the EU —
as *implemented acquisition paths*. What has actually been ingested, and where, is stated below and
is much narrower. That distinction is the point, not a hedge.

## The bet

The thesis is [ADR-0033](docs/adr/0033-agentic-legal-reasoning.md): **a thorough data platform for
law makes the AI use cases easy.** So the deliverable is not a corpus. It is the loop that produces
one:

```text
blueprint template → source version → acceptance run → evidence → enabled: true → approval
```

The corpus is that loop's output. The measure of the platform is what the *n*th jurisdiction costs,
and the acceptance test is ADR-0033's dog question — what rules bind a dog owner in Zürich, which
requires walking `BV → TSchG/TSchV → cantonal Hundegesetz → communal Vollzugsvorschriften` —
answered over a corpus assembled through the platform, or **refused correctly** because the
governing ordinance is not in it. The refusal counts as much as the answer.

ADR-0033 §4 is a standing guardrail: the MCP server does not get built first. Over today's corpus it
would demo convincingly and be wrong.

## Status — what exists, and in which environment

**The loop runs end to end.** Acquisition → artifact bundle → document-intelligence → canonical
document → OpenSearch projection → search UI, on Docker Compose, brought up and self-verified by
[`scripts/dev-loop-stack.sh`](scripts/dev-loop-stack.sh).

**Acquisition providers.** Twelve are registered, plus a fixture-replay provider for shadow runs
([`provider_registry_factory.py`](platform-control/src/platform_control/services/provider_registry_factory.py)).
Each carries a code-owner readiness state —
`scaffold` / `awaiting_evidence` / `live` — defined in
[`acquisition_core/providers.py`](platform-control/src/acquisition_core/providers.py). `fedlex_sparql`,
`ris_ogd`, `eur_lex_sparql`, `deterministic_http`, `bundesland_http`, `regione_http`, `lexfind_api`
and `gemeinde_http` are `live`; `ch_court_decisions` is `awaiting_evidence`; `canton_http` and
`legifrance` are `scaffold` — registered so templates parse, and unable to dispatch any run.

**Acceptance evidence exists for the cantonal and communal rungs, in `compose-local` only.** Four
ADR-0030 bundles under [`docs/runbooks/evidence/`](docs/runbooks/evidence/) — Zürich (v3), Bern,
Basel-Stadt via LexFind, and Stadt Zürich via `gemeinde_http` — every one recording
`Environment: compose-local`, `execution_mode: live` against the real portal, and `skipped_gates=[]`.
The ZH bundle captured 4 PDFs, put 4/4 through document-intelligence, and returned 9 search hits.

**No cantonal or communal blueprint template is turned on.** `enabled` is the operator-owner key of
the ADR-0030 two-key lock and it fails closed. In
[`source_blueprints.yaml`](platform-control/src/platform_control/hierarchies/source_blueprints.yaml)
17 templates are `enabled: true` and 17 are `enabled: false` — and every LexFind, `gemeinde_http`,
`canton_http`, court-decision and federal animal-protection template is among the `false` ones.
So the acquired Swiss cantonal and communal corpus exists in a local compose stack and nowhere else.
The evidence was captured in an environment that is not the deployed one, and the config key that
would let a production run fire has deliberately not been turned.

**What that means, plainly:** this repository holds a working platform and a demonstrated loop. It
does not hold Swiss law. Three cantons *onboarded* is not three cantons *held* — the ZH acceptance
searched one branch of the systematic numbering (554.\*), not the canton. `lexfind_api_zh_full`
exists and enumerates the whole canton (1377 records against a published denominator of 1377), and
it too ships shut.

**Coverage is a measured API, not a vibe.** `GET /v1/acquisition-coverage`
([`routers/coverage.py`](platform-control/src/platform_control/routers/coverage.py)) reports
expected → discovered → acquired → processed per jurisdiction and refuses to publish a completeness
score; legal-search serves the corpus-side `/v1/coverage` (ADR-0042, ADR-0048). A run that an
operator deliberately capped reports a truncated denominator rather than a fake coverage failure.

**Not built:** hybrid retrieval, and the MCP server that would sit on it.

### Direct from the source, and where that is qualified

Every blueprint template records `source_origin_kind: official_primary` and a `trust_tier`, and the
acquisition path fetches from the issuing body. One path is a mirror and says so:
[`lexfind_api_provider.py`](platform-control/src/platform_control/services/lexfind_api_provider.py)
acquires cantonal legislation through LexFind (a project of the Schweizerische
Staatsschreiberkonferenz, 26 cantons + Bund behind one unauthenticated JSON API) rather than from
each canton's own portal, because for Zürich the canton's own portal *cannot* be scraped — its
`erlass-*.html` pages are metadata-only and the host holding the text refuses TCP. The mirror is
justified rather than assumed: the mirrored file is md5-identical to the canton's own
(`461c614535cb7b5aa33175904f7d3229`, verified both ways), and every record keeps the canton's
`original_url` so the canonical citation survives the mirror.

## Quickstart

**Docker is the only real prerequisite** (plus `curl`, which the verify step uses). Every service
builds and runs in a container — the seed step runs inside `node:22-alpine` — and the local stack
runs keyless by design. No cloud account, API key or credential.

```bash
git clone <repo-url> evidara     # the directory must be named `evidara`
cd evidara
bash scripts/dev-loop-stack.sh up
```

`up` rebuilds every image, brings up the acquisition→search loop, and then **verifies it against the
repo** rather than trusting that every container reports healthy. It exists because the loop has
settings that are inert by default and silent when wrong: a `noop` event publisher makes runs appear
to hang at `canonical_ready=0` with no error anywhere, and a stale `platform-control-init` image
reports migration success while applying nothing. It ends by printing either
`Stack is consistent with the repo.` or the specific invariant that failed.

> The clone directory must be `evidara`: verify addresses containers by their Compose project name
> (`evidara-platform-control-api-1`), which Compose derives from the directory.

| Surface | URL |
|---|---|
| Search UI | <http://localhost:3101> |
| Operator admin | <http://localhost:3100> |
| Search API | <http://localhost:3102/health> |
| Control plane API | <http://localhost:8000/health> |

**What you get:** a smoke corpus of 20 Swiss court decisions pulled at bring-up from the public
`voilaj/swiss-caselaw` HuggingFace dataset
([`seed-from-opencaselaw.ts`](legal-search/api/scripts/seed-from-opencaselaw.ts)). It is a smoke
corpus, not a legal library — searching for Swiss legislation returns nothing until you run an
acquisition through the control plane, which is the loop this platform is about.

`bash scripts/dev-loop-stack.sh verify` re-checks a running stack. `down` stops it **and removes
volumes**.

To drive the loop itself — pick a template, preflight it, run it, watch it, capture its evidence —
use [`tools/evidara-cli`](tools/evidara-cli/README.md) (`evidara workflow coverage …`) or the admin
UI. `scripts/local-vertical-slice.sh` is the lighter alternative when you only need plain
dependencies; it predates ADR-0029 and brings up neither NATS nor MinIO, so the event path is not
configured and the loop will not complete. `npm run dev:cross-surface:live` runs the two frontends
as dev servers against a lean stack; it requires Node and npm on the host and does **not** install
dependencies, so run `npm ci` in each surface first.

## Repository map

| Folder | Purpose |
|--------|---------|
| [`legal-search/`](legal-search/) | Next.js frontend + NestJS BFF for search and document detail. Two independent npm packages, not a workspace |
| [`marketing/`](marketing/) | Public waitlist / positioning page (Next.js static export; the only public surface — ADR-0039) |
| [`platform-control/`](platform-control/) | Source lifecycle, runs, approvals, reference data (FastAPI); `admin/` is the React-admin ops UI |
| [`document-intelligence/`](document-intelligence/) | Raw-to-canonical processing pipelines (containerized NATS JetStream consumer; Spark/Databricks opt-in only — ADR-0029) |
| [`contracts/`](contracts/) | OpenAPI specs, JSON Schemas, event schemas (build-time only) |
| [`infra/`](infra/) | Terraform, deployment configs, environment definitions |
| [`docs/`](docs/) | Architecture, ADRs, runbooks, testing strategy, component docs |
| [`tools/evidara-cli/`](tools/evidara-cli/) | Typer CLI for agent/operator smoke against platform-control + legal-search |
| [`country-overlays/`](country-overlays/) | Per-jurisdiction reference data and operator/user content overlays |
| [`scripts/`](scripts/) | Shared tooling and the repo's quality gates |
| [`structurizr/`](structurizr/) | `workspace.dsl` — the canonical architecture model |
| [`vendor/`](vendor/) | Vendored external pins (see the MacConfig section below) |
| [`k8s/gitops/`](k8s/gitops/), [`service-template/`](service-template/) | Argo CD Kustomize roots and manifest conventions |

Contracts live at the repo root only, never inside a component (ADR-0004). Repo-wide conventions —
including the per-surface quality gates — are in [`AGENTS.md`](AGENTS.md).

## How this is built

**Contract-first, and contracts are generated where they can be.** APIs are defined in
[`contracts/api/`](contracts/api/), not invented inline.
`contracts/api/platform-control.openapi.yaml` is *generated* from the FastAPI app and drift-gated in
CI (ADR-0034) — hand-maintaining it had let it drift to 4 of 11 acquisition providers and shipped
two bugs.

**Guards, not vigilance.** [`scripts/`](scripts/) holds over ninety scripts, three dozen of them
`check_*` gates that fail the build when docs, contracts, index mappings or config drift apart. Each
exists because something specific went wrong once, and the comment at the top of the file says what.
A convention nobody *can* forget beats one everybody is asked to remember.

**Evidence over green.** A passing run is not automatically evidence (ADR-0040). Skipped gates count
as unverified, not verified; a run replaying fixtures cannot certify a live source; a verdict that
cannot tell "delivered" from "not observed" is not a pass.

**Layered tests**, including a compiled-artifact level that exists because a decorator-metadata bug
shipped a silently inert query parameter to production that no unit or integration test could see.
See [docs/testing/testing-levels.md](docs/testing/testing-levels.md).

**AI-native, and explicit about it.** Much of this was built by directing AI agents, and the commit
log says so. [`AGENTS.md`](AGENTS.md) carries the conventions and `.claude/skills/` holds
task-specific operating procedures — the guard scripts matter more in an agent workflow than a human
one, because the failure mode is speed without memory.

## Where to start reading

- [ADR-0033 — Agentic legal reasoning](docs/adr/0033-agentic-legal-reasoning.md) — the thesis and
  the build order it forces.
- [ADR-0030 — Acquisition provider enablement lifecycle](docs/adr/0030-acquisition-provider-enablement-lifecycle.md)
  — the two-key lock, and why an acceptance run is allowed to precede both keys.
- [ADR-0042](docs/adr/0042-corpus-coverage-as-an-api.md) and
  [ADR-0048](docs/adr/0048-completeness-crosses-the-boundary-by-projection.md) — what a coverage
  answer may and may not be read to mean.
- [`docs/adr/`](docs/adr/) — the full decision record, numbered through ADR-0048, including the
  decisions that reversed earlier ones.
- [System Context](docs/architecture/system-context.md) and
  [Boundary Contracts](docs/architecture/boundary-contracts.md) — the architecture narrative.
- [`docs/testing/`](docs/testing/) — what each test level is for, and what it cannot see.
- [`docs/components/`](docs/components/) — per-component guidance.

## Main interaction flow

```text
platform-control → document-intelligence → legal-search
```

- **platform-control** manages sources, versions, runs and approvals, and triggers acquisition.
- **document-intelligence** receives immutable artifact bundles and produces canonical structured
  documents.
- **legal-search** consumes canonical truth, projects it into OpenSearch, and serves search.

## Working on it

The Quickstart needs only Docker. Developing on a surface needs more, and the versions are not
advisory:

- **Node 22** (`.nvmrc`; `engines` pins `>=22 <24`). Node 24+ ships a built-in `localStorage` that
  shadows jsdom's under Vitest and breaks tests that pass in CI. Run `nvm use`.
- **`uv`** for the Python surfaces (`platform-control`, `document-intelligence`, `tools/evidara-cli`).
- **Docker** again for `legal-search/api`'s gate — its integration layer runs Testcontainers against
  a real OpenSearch, the only level that meets a real index mapping.
- **`pyyaml`** for the `scripts/` tests; run them as
  `uv run --with pyyaml python -m unittest discover -s scripts/tests -p "test_*.py"`.

There is no repo-wide command. Each surface has its own gate — see the table in
[`AGENTS.md`](AGENTS.md) and run the narrowest one for what you touched. Developer CLIs
(`kubectl`, `helm`, `terraform`, `jq`, `shellcheck`, `uv`) are workstation-managed; the repo ships
no shell.

## MacConfig platform contract

Evidara vendors a pinned copy of the MacConfig cluster platform contract from
`clusters/prod/platform-contract.yaml` in the [MacConfig](https://github.com/philipplukas/MacConfig)
repository (`vendor/platform-contract.yaml` here). To refresh: in a MacConfig checkout run
`make platform-contract-path` (prints the absolute path), copy that file here, then set the pin
below to the same value as `contractVersion` in the YAML; CI enforces they stay in sync.
Operator playbooks: [`docs/migration/`](docs/migration/README.md).

**Pinned MacConfig platform contract:** `0.1.0`

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md). This is primarily a
single-author project — issues and discussion are more useful than large unsolicited pull requests.
