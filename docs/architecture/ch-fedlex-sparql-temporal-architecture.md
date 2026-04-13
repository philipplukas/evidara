# CH Fedlex SPARQL Provider and Temporal Orchestration

## Status

Proposed implementation path for CH Fedlex after the first live deterministic thin slice on
`dev`.

## Purpose

Define the production-safe CH Fedlex architecture after the live evidence showed:

- raw `www.fedlex.admin.ch` and `fedlex.data.admin.ch` document URLs are not suitable as plain
  `deterministic_http` seeds
- the public Fedlex data surface is queryable through SPARQL
- Temporal is useful for orchestration, retries, hierarchy traversal, and backfills, but it is not
  the acquisition provider itself

This document separates:

1. `how to fetch CH Fedlex data deterministically`
2. `how to orchestrate large-scale CH scraping, retries, and backfills`

## Problem statement

The first live CH deterministic run proved the platform path works but the acquisition config is
wrong for Fedlex text capture.

Observed facts:

- `deterministic_http_fedlex_legislation` seeded `https://www.fedlex.admin.ch/`
- the run completed successfully end to end
- the captured artifact was only the Fedlex homepage shell
- direct GETs to document-looking `/eli/...` URLs still returned SPA shell content or `400`
- the Fedlex metadata app rendered real legal metadata only after browser-side query execution

At the same time, live probing confirmed:

- public SPARQL endpoint: `https://fedlex.data.admin.ch/sparqlendpoint`
- work URI example: `https://fedlex.data.admin.ch/eli/cc/1999/404`
- work -> language expressions can be resolved deterministically via SPARQL:
  - `.../de`
  - `.../fr`
  - `.../it`
  - `.../en`
  - `.../rm`

## Core decision

Use a CH/Fedlex-specific deterministic provider built on top of SPARQL resolution.

Do **not** use Firecrawl as the long-term CH production path.

Use Temporal above the provider for:

- hierarchy traversal
- shard fan-out
- retries
- resume/checkpoint behavior
- backfill windows
- optional human approval gates before widening/promotion

## Boundary: provider vs Temporal

### Provider owns

- resolving a Fedlex work URI into language expressions
- resolving expression/work nodes into text-bearing or manifestation-bearing targets
- fetching deterministic payloads
- emitting provider resources for raw artifact persistence
- preserving authoritative metadata in resource metadata/provenance

### Temporal owns

- choosing which work URIs to process
- partitioning large CH hierarchies into shards
- retrying failed shards
- resuming long-running backfills
- enforcing batch sizes and backpressure
- scheduling periodic refresh or date-window backfills
- optionally gating scale-up or promotion after a pilot shard

### Why this split is correct

The current repo already separates these concerns:

- acquisition runs are created through `POST /v1/runs`
- run dispatch uses the provider registry / connector worker
- Temporal today is used by the wizard/orchestrator path, not as the run provider

Relevant current implementation surfaces:

- provider registry: [provider_registry_factory.py](../../platform-control/src/platform_control/services/provider_registry_factory.py)
- run dispatch: [run_service.py](../../platform-control/src/platform_control/services/run_service.py)
- connector worker: [connector_worker.py](../../platform-control/src/platform_control/connector_worker.py)
- Temporal orchestrator: [orchestrator.py](../../platform-control/src/platform_control/services/orchestrator.py)
- rollout guide: [platform-control-wizard-temporal-argilla-rollout.md](../setup/platform-control-wizard-temporal-argilla-rollout.md)

## Proposed CH provider

Name suggestion:

- `fedlex_sparql`

### Minimal provider responsibilities

Given a source version acquisition spec, the provider should:

1. take one or more seed work URIs
2. query Fedlex SPARQL for the work node
3. resolve language expression URIs from `jolux:isRealizedBy`
4. choose the preferred language set from acquisition config
5. resolve text-bearing, manifestation-bearing, or section-bearing targets for those expressions
6. fetch the resolved targets deterministically
7. emit provider resources with:
   - `source_url`
   - `final_url`
   - content type
   - fetched body
   - title / metadata when available
   - provenance metadata including work URI, expression URI, language, and query mode

### Acquisition spec shape

The current union contains:

- `deterministic_http`
- `firecrawl`
- `ris_ogd`

CH should likely add a new acquisition spec/provider family rather than overloading
`deterministic_http`.

Illustrative shape:

```yaml
provider: fedlex_sparql
seed_work_uris:
  - https://fedlex.data.admin.ch/eli/cc/1999/404
preferred_languages:
  - de
  - fr
manifestation_preference:
  - html
  - xml
  - pdf
query_mode: work_to_expression
max_expressions: 5
```

### Immediate first slice

For the first CH implementation, keep it intentionally narrow:

- one known work URI
- one preferred language (`de`)
- one bounded resolution path
- one preview run

That keeps the provider small while proving the correct architecture.

## Proposed CH workflow path

### Phase 1: source and version setup

Operator path stays in `platform-control`:

1. create source
2. create source version
3. approve source version

At this point we have frozen configuration but no large-scale orchestration yet.

### Phase 2: preview run through provider

For the narrow pilot:

1. `POST /v1/runs`
2. run service resolves provider by acquisition spec
3. provider performs SPARQL resolution + deterministic fetch
4. platform-control persists raw artifacts and bundle manifests
5. document-intelligence processes the artifacts
6. `document.processing_status.updated` and `document.processed` flow back
7. operator reviews run-scoped evidence

This phase does **not** require Temporal.

### Phase 3: Temporal for scaled CH execution

Once the provider is proven for one work:

1. Temporal workflow chooses a set of work URIs or hierarchy shards
2. child workflows create run batches
3. each run still goes through the same provider registry path
4. workflow observes terminal states and downstream health
5. failed shards are retried or quarantined
6. successful shards advance the checkpoint

This is where Temporal adds value.

## End-to-end step map

```mermaid
flowchart TD
  A["Operator approves CH source version"] --> B["Platform-control run created"]
  B --> C["Provider registry resolves fedlex_sparql provider"]
  C --> D["Provider queries Fedlex SPARQL for work URI"]
  D --> E["Provider resolves expression URIs"]
  E --> F["Provider resolves text/manifests and fetches deterministic payloads"]
  F --> G["Platform-control writes raw artifacts + bundle manifest"]
  G --> H["artifact_bundle.available emitted"]
  H --> I["Document-intelligence processes bundle"]
  I --> J["document.processing_status.updated emitted"]
  I --> K["document.processed emitted"]
  K --> L["Legal-search projection/index update"]
  L --> M["Search/detail available"]
```

### Where Temporal fits

Temporal sits above step `B` when we scale:

```mermaid
flowchart LR
  T["Temporal CH workflow"] --> S["Shard work URIs / backfill window"]
  S --> R["Create platform-control run(s)"]
  R --> P["fedlex_sparql provider path"]
  P --> O["Observe outcomes + retry failed shards"]
  O --> C["Checkpoint / continue_as_new / promotion gate"]
```

## Retry and backfill model

### Provider-level retry

Use normal run retry only for:

- transient query transport failures
- temporary Fedlex endpoint availability issues
- transient downstream publish problems

Do not blindly retry:

- empty or low-value content caused by bad resolution logic
- wrong language selection
- wrong work/expression targeting

### Temporal-level retry

Temporal should own:

- shard retries
- resume from last successful shard or date window
- backfill by changed effective-date bands
- throttling large CH hierarchy expansions

### Backfill candidates

Good CH backfill shapes for Temporal:

- changed federal work URIs since a given checkpoint
- per-language shard
- date-window membership URIs
- section/article subtree replay after parser changes

## Relation to current run backends

Current platform-control runtime has two distinct orchestration layers:

1. `run_dispatch_backend`
   - `inline` or `worker`
   - controls whether connector execution happens inside the API request or via the connector worker

2. `wizard_orchestrator_backend`
   - `in_memory` or `temporal`
   - controls the wizard/human-gate orchestration path

Important implication:

- changing CH acquisition to SPARQL does not require changing the wizard backend immediately
- the CH provider can be introduced through the existing provider registry first
- Temporal can be added as the scale/backfill controller after the provider is proven

## Recommended implementation order

1. Add a narrow `fedlex_sparql` provider.
2. Add one CH source version using that provider for a known work URI.
3. Run one preview on `dev`.
4. Confirm:
   - real legal content is captured
   - artifact bundle is valid
   - DI reaches `canonical_ready`
   - search/detail path is plausible
5. Only then add Temporal orchestration for:
   - hierarchy fan-out
   - retries
   - backfills

## What not to do

- Do not keep widening the current `deterministic_http_fedlex_legislation` homepage seed.
- Do not make Firecrawl the CH production acquisition path just because it can render pages.
- Do not collapse provider logic into Temporal workflow code.
- Do not make Temporal mandatory for the very first CH proof run.

## Immediate next actions

1. Define the new CH acquisition contract for `fedlex_sparql`.
2. Implement a minimal provider in `platform-control`.
3. Add a CH source blueprint/template that targets a work URI, not the homepage root.
4. Run one preview on `dev`.
5. If successful, design the Temporal shard/backfill workflow around that provider.
