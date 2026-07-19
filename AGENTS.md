# AGENTS.md

## Purpose

This is the Evidara monorepo — a document intelligence platform for legal research. It contains:

- **legal-search** — Next.js frontend + NestJS BFF for search and document detail
- **marketing** — public waitlist / positioning page (Next.js static export; the only public surface — see ADR-0039)
- **platform-control** — Source lifecycle, runs, approvals, reference data (Cloud Run)
- **document-intelligence** — Raw-to-canonical processing pipelines (containerized NATS JetStream consumer; Spark/Databricks is opt-in only — see ADR-0029)
- **contracts** — OpenAPI specs, JSON Schemas, event schemas (build-time only)
- **infra** — Terraform, deployment configs, environment definitions
- **docs** — Architecture, ADRs, runbooks, testing strategy, component docs
- **tools/evidara-cli** — Typer CLI for agent/operator smoke against platform-control + legal-search (`evidara --help`); optional `EVIDARA_CLI_SMOKE=1 bash scripts/smoke-evidara-cli.sh` when both APIs are reachable; against **private Cloud Run** use [`scripts/mint-cloud-run-tokens.sh`](scripts/mint-cloud-run-tokens.sh) and [docs/setup/gcp-local-cloud-run-auth.md](docs/setup/gcp-local-cloud-run-auth.md)

**Developer tooling is workstation-managed.** There is no repo-managed shell — install CLIs
(`kubectl`, `helm`, `terraform`, `jq`, `shellcheck`, `uv`, …) with your OS package manager.
The Nix flake that used to provide `nix develop` was removed; do not reintroduce a repo-level
tool manager without an ADR.

**Parallel work streams** (by component, what to serialize): [docs/process/parallel-work-streams.md](docs/process/parallel-work-streams.md).

## Core rules

1. **Small, production-safe changes.** Prefer focused commits over sweeping refactors.
2. **Follow existing patterns.** Before introducing a new abstraction, check if the repo already has one. Grep before you create.
3. **Edit over duplicate.** Prefer modifying existing files over creating parallel abstractions.
4. **Generated over handwritten.** Prefer generated reference docs (OpenAPI, terraform-docs, TypeDoc) over manually maintained reference tables.
5. **Contract-first.** APIs are defined in `contracts/api/`, not invented inline. The spec is the source of truth — **except `contracts/api/platform-control.openapi.yaml`, which is generated from the FastAPI app** (ADR-0034). It is still the contract; it is just no longer hand-written. Change the routers/schemas and regenerate — `scripts/check-platform-control.sh` fails the build if the file and the app disagree. Hand-maintaining it is what drifted it to 4 of 11 acquisition providers and caused #614/#616 (see #618).

## Change classification

Every change should be classified as one or more of:

- `internal-refactor` — restructuring without behavior change
- `user-visible-behavior` — changes what users see or experience
- `contract-change` — API specs, event schemas, shared entity shapes
- `infra-change` — Terraform, deployment, cloud resources
- `pipeline-change` — document-intelligence processing, data quality
- `architecture-change` — domain boundaries, storage decisions, communication patterns
- `docs-only` — documentation without code

## Required sync checks by change type

### user-visible-behavior

Update as applicable:

- Focused tests (narrowest test that proves the change)
- Feature docs in `docs/components/` or `legal-search/docs/`
- Runbook if operator flow changed

### contract-change

Update as applicable:

- OpenAPI spec in `contracts/api/`
- JSON Schema in `contracts/schemas/` or `contracts/events/`
- Generated clients (`npm run openapi:generate` in `legal-search/frontend/`)
- Contract tests and schema validation

### infra-change

Update as applicable:

- Terraform docs (generate, don't hand-maintain)
- `docs/setup/` guides
- Runbook if deployment or recovery changed

### pipeline-change

Update as applicable:

- Data quality checks
- Pipeline docs
- Failure-mode notes and recovery instructions

### architecture-change

Update as applicable:

- `structurizr/workspace.dsl` (canonical architecture)
- ADR in `docs/adr/` for significant decisions
- `docs/architecture/` for narrative docs
- Mermaid diagrams only in docs pages for explanation

## Evidara-specific rules

### Contract location

All shared contracts live at `contracts/` (monorepo root). Never inside a component folder. See ADR-0004.

### legal-search stack

`legal-search/` is a plain directory holding two **independent** npm packages. It is
**not** an npm workspace root and has no `package.json` — never run `npm install`
there (it used to hold a vestigial package that ERESOLVEs; see #588). Install and
run gates inside each package:

- `frontend/` — Next.js application (user-facing search and document detail)
- `api/` — NestJS application (search and document endpoints, OpenSearch adapter)

### JavaScript dependency resolution (read before touching node_modules)

The repo is **not** an npm workspace. Each JS surface (`legal-search/frontend`,
`legal-search/api`, `platform-control/admin`, `marketing`) owns its
`node_modules`, and CI installs them per-surface with `npm ci`.

- **Node is pinned in `.nvmrc` (22)** and enforced via `engines`. Node >= 24 ships an
  experimental built-in `localStorage` that shadows jsdom's under Vitest, silently
  breaking tests that pass in CI. Run `nvm use`.
- **The repo-root `node_modules` must never be a symlink.** The root package
  (`evidara-doc-tools`) is not a workspace root; nothing should resolve through it.
- The shared modules under `styles/` (`@evidara/ui`, `@evidara/tokens`,
  `@evidara/shell`) live **outside any package**, so their bare imports (`react`,
  `clsx`, `lucide-react`, `tailwind-merge`) must be resolved from the **consuming**
  surface — via `tsconfig` `paths`, Vitest `resolve.dedupe`, and Turbopack
  `resolveAlias`. Resolving them anywhere else yields a **second React instance**
  ("Cannot read properties of null (reading 'useContext')").

`bash scripts/check-js-workspace-hygiene.sh` guards all of the above and runs in both
pre-commit and CI.

**frontend:**

- **Design tokens** live in `globals.css` as CSS custom properties. Use `var(--token)` everywhere, never hardcoded colors.
- **Biome** for linting and formatting (not ESLint). Config in `legal-search/frontend/biome.json`.
- **Vitest** for tests. Config in `legal-search/frontend/vitest.config.ts`.
- **Orval** generates typed clients from OpenAPI. Two outputs: fetch client (Server Components) and React Query hooks (client components). See ADR-0007.
- **`npm run check`** is the pre-commit quality gate (typecheck + lint + test).
- **`npm run openapi:check`** is the CI drift gate (generate + git diff).

**api:**

- **NestJS** with TypeScript. See ADR-0008 for full conventions.
- **Repository interface pattern** — OpenSearch logic only in adapters, never in controllers or services.
- **Spec-first** — `contracts/api/legal-search.openapi.yaml` is canonical. Swagger decorators are additive for dev UI only.
- **Global pipes/filters** — ValidationPipe (whitelist, transform), AllExceptionsFilter, CorrelationIdMiddleware.
- Test layers: unit (fast, mocked), integration (Testcontainers OpenSearch), smoke (HTTP-level).
  The integration layer (`src/**/*.integration.spec.ts`, run by `npm run test:integration`, which
  `npm run check` invokes) needs a running **Docker daemon**. It is the only layer that meets a real
  index mapping — see [docs/testing/testing-levels.md](docs/testing/testing-levels.md) Level 4 and
  #672/#673/#675 for why mocking it away is not an option.
- **The documents-index mapping has one source of truth**:
  `legal-search/api/src/core/opensearch/documents-index.mapping.ts`. Every producer derives from it —
  `documents-bootstrap.ts` (runtime + seed + cutover) directly, and non-TypeScript producers via the
  generated `scripts/opensearch/documents-index.mapping.json` (`npm run mapping:generate`, drift-gated
  by `documents-index.mapping-json.spec.ts`). Never hand-maintain a parallel copy: a drifted copy in
  `scripts/validate-tar89-metadata-local.sh` is what caused #675, and a mapping-less `PUT` in the GCP
  runtime tfvars was the same defect again (#713). Because OpenSearch returns empty
  buckets rather than an error for a missing field, both presented as query bugs for months.
  Index creation is first-writer-wins, so a second creation path does not merely disagree with the
  canonical one — it silently *wins* over it. Producers go through `createDocumentsIndex()` in
  `documents-bootstrap.ts` and are enumerated in `PRODUCERS` in `mapping-drift.integration.spec.ts`;
  a producer that cannot be added to that registry is by definition drifting.
  When a live index disagrees with the canonical mapping, **fix the index** (reindex/cutover) — never
  weaken the query to match the drift. `npm run mapping:check-drift` reports the difference against a
  live cluster; `mapping-drift.integration.spec.ts` guards the creation path in CI.

### platform-control stack

- **FastAPI** with Python 3.12+. See ADR-0009 for full conventions.
- **Pydantic v2** for request/response validation.
- **SQLAlchemy + Alembic** for ORM and migrations.
- **uv** for dependency management.
- **React-admin** (`platform-control/admin`, Next.js) is the ops UI — it uses the platform-control API only (no direct Postgres from the browser). See ADR-0009 and ADR-0015. Archived Retool artifacts live under `platform-control/retool/` for historical comparison only (ADR-0006 superseded).
- **Action-focused API** — endpoints cover state transitions, webhooks, and operator read models consumed by the admin app.
- Test layers: unit (state machines, service logic), integration (Testcontainers Postgres), smoke (HTTP-level).
- **`ruff check` + `ruff format`** for linting and formatting (not flake8/black).
- **`pytest`** for all tests.
- **`pyproject.toml`** is the single config file — no `setup.py`, no `requirements.txt`.

### Language split

| Component | Language | Why |
|-----------|----------|-----|
| `legal-search/frontend` | TypeScript / Next.js | User-facing UI |
| `legal-search/api` | TypeScript / NestJS | Search and document API |
| `platform-control` | Python / FastAPI | Consistent with data infrastructure |
| `document-intelligence` | Python | Data processing pipelines (containerized consumer; Spark/Databricks opt-in) |
| `infra` | HCL / Terraform | Infrastructure as code |

The pre-commit hooks and CI workflows must run the same checks. If you add a check to one, add it to the other. `scripts/` is the shared entry point.

### Source of truth hierarchy

| Thing | Source of truth |
|---|---|
| Architecture | `structurizr/workspace.dsl` |
| API interfaces | `contracts/api/*.openapi.yaml` — hand-authored, except `platform-control.openapi.yaml`, which is **generated** from the FastAPI app by `scripts/generate_platform_control_contract.py` and drift-gated (ADR-0034) |
| Entity shapes | `contracts/schemas/*.json` |
| Event payloads | `contracts/events/*.json` |
| Infra resources | `infra/terraform/` |
| Design tokens | `styles/tokens/tokens.css` (shared; see ADR-0027 — "two products, shared brand"). Workspace-local extensions: `legal-search/frontend/src/app/globals.css`; admin-local: `platform-control/admin/src/app/globals.css`; marketing-local: `marketing/src/app/globals.css`. |
| Public marketing copy | `marketing/src/lib/content.ts` — every claim carries an `evidence` code path; `content.test.ts` fails the build on a claim without one (ADR-0039) |
| Tests | Test files adjacent to code |
| Narrative docs | `docs/` |

## Testing policy

Always add or update the **narrowest test** that proves the change:

- Unit test for local logic
- Integration/contract test for interfaces
- Smoke/e2e only when required for user-visible flows

Do not add large brittle tests when a small test proves the change.

## Documentation policy

Update docs when any of these change:

- User-visible behavior
- Setup/run workflow
- Architecture boundaries
- Dependencies between systems
- Contracts or schemas
- Operator procedures

If no docs change is needed, explain why in the PR.

## PR completion rules

A PR is not complete if applicable sync surfaces were ignored.

Before finalizing, verify:

- [ ] Code is updated
- [ ] Tests are updated (or explain why not)
- [ ] Contracts are updated if needed
- [ ] Docs are updated if needed
- [ ] Architecture is updated if needed

## Working guidance for AI

### Verify against code, not against issue text

**Establish the baseline from the repository before you change anything.** Issue bodies, ADRs,
PR descriptions and code comments record what was true when written. This repo moves fast enough
that they are routinely stale — and stale in both directions.

Before acting on a stated problem:

- Read the code on current `origin/main` and cite `file:line` for what you find.
- Check whether a merged PR already resolved it (`git log --grep`, the issue's cross-references).
- Treat an **open** PR as resolving nothing — a fix in flight means the issue is still live.
- Check in-flight PRs for anything you are about to claim exclusively (an ADR number, a
  `contracts/manifest.yaml` version, a new file path). Reading `main` alone will not show them.
- If the stated diagnosis is wrong, say so and fix the real defect. Do not implement a fix aimed
  at a cause that does not exist.

If the issue turns out to be resolved, or wrong, **that is a valid and useful outcome** — report it
with evidence instead of manufacturing work to match the ticket.

The same applies to a green test suite: see the testing-trust rules on when a passing run is and
is not evidence.

### Report what you found, not what was expected

State honestly when a result contradicts the brief you were given, including a brief from another
agent or from the repo owner. A correction backed by `file:line` is worth more than agreement.

## Review guidance for AI

Flag or warn if:

- Behavior changed but no test changed
- Contract changed but schema/spec/docs did not
- Terraform changed but docs were not regenerated
- Architecture boundary changed but Structurizr was not updated
- Docs were manually edited where generation should be used
- Changes are large, duplicative, or inconsistent with repo patterns
- Design tokens are hardcoded instead of using CSS custom properties
- OpenAPI clients are hand-written instead of generated
- New patterns conflict with established conventions
