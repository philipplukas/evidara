# CH Fedlex Fast-Loop Backlog

Owner: Platform / GA  
Last reviewed: 2026-04-14  
Last verified: 2026-04-14  
Status: Active implementation backlog  
Applies to: CH Fedlex provider iteration on `dev`

## Purpose

Turn the successful CH Fedlex SPARQL proof into a fast, mostly autonomous iteration loop.

The target loop is:

1. change `fedlex_sparql`
2. validate locally
3. deploy only `platform-control-api-dev`
4. run one tiny CH preview
5. auto-check acquisition + DI + lifecycle + basic content quality
6. decide `keep`, `fix`, or `widen`

This backlog is the execution companion to:

- [CH Fedlex SPARQL Provider and Temporal Orchestration](../architecture/ch-fedlex-sparql-temporal-architecture.md)
- [CH + AT Thin-Slice Execution](ch-at-thin-slice-execution.md)
- [Five-Country Acceptance A (CH + AT)](five-country-acceptance-a.md)
- [Friction and Acceleration Map](friction-and-acceleration-map.md)

## Current baseline

Proven on `dev`:

- `fedlex_sparql` resolves a work URI to a Fedlex HTML manifestation
- `platform-control-api-dev` on revision `platform-control-api-dev-00038-5ng` processed a bounded CH preview successfully
- run `run_01kp5b2rjvrkdd1d8d1a946b5b` captured:
  - `content_type=text/html`
  - one raw artifact
  - one captured resource
  - downstream processing states `accepted`, `processing`, `canonical_ready`
  - lifecycle event `document.processed`

Known friction:

- the full runtime image pipeline is too broad for provider-only iteration
- heavy runner label churn still exists
- heavy runner egress to `docker.io` and `docker.pkg.dev` is flaky over IPv6
- we needed a manual registry-copy workaround to unblock the latest `platform-control` deploy

## Primary objective

Get to a single operator command that can produce a reliable pass/fail result for the narrow CH slice
in under 10 minutes.

## Workstreams

### Track 1: platform-control-only fast deploy path

#### Task 1.1: Build a `platform-control-only` image workflow

Goal:

- build and publish only `platform-control`

Scope:

- new GitHub Actions workflow dedicated to `platform-control` image build
- tags with full SHA, matching current Artifact Registry conventions
- no dependency on frontend, admin, legal-search, or document-service images

Definition of done:

- dispatchable on `main` and manually
- publishes `platform-control:${sha}` to Artifact Registry
- completes without waiting on unrelated image jobs

Acceptance checks:

- artifact exists in Artifact Registry under the full SHA tag
- workflow summary includes image reference

#### Task 1.2: Build a `platform-control-only` dev deploy workflow

Goal:

- deploy only `platform-control-api-dev`

Scope:

- new workflow or split path in existing CD
- update only `platform-control-api-dev`
- optional separate support for `platform-control-worker-dev`, but not required for the first loop

Definition of done:

- manual dispatch deploys a given SHA tag to `platform-control-api-dev`
- workflow verifies latest ready revision after deploy
- workflow runs `/health` and `/ready`

Acceptance checks:

- `gcloud run services describe platform-control-api-dev` shows the requested tag
- health and readiness steps pass

#### Task 1.3: Document when to use fast deploy vs full runtime CD

Goal:

- stop mixing provider iteration with full platform release workflows

Definition of done:

- short runbook section in the operator docs
- clear rule:
  - provider iteration -> fast deploy path
  - release validation -> full runtime CD

### Track 2: CH fast smoke command

#### Task 2.1: Add `scripts/ch-fedlex-fast-loop.sh`

Goal:

- make the successful CH preview sequence reproducible with one command

Script responsibilities:

- resolve dev URLs
- mint Cloud Run tokens
- create source + source version
- check readiness
- approve version
- launch bounded preview
- poll run status
- poll provider jobs
- poll preview summary
- poll processing status
- poll document lifecycle
- print a single verdict block

Definition of done:

- one command runs the full narrow preview against `dev`
- writes all API payloads to a timestamped temp directory
- exits nonzero on failed gates

Expected outputs:

- `source_id`
- `source_version_id`
- `run_id`
- final run status
- content type breakdown
- processing status summary
- lifecycle summary

#### Task 2.2: Add flags for iterative use

Required flags:

- `--env`
- `--template`
- `--max-resources`
- `--json`
- `--keep-source`

Nice-to-have later:

- `--source-id`
- `--source-version-id`

Shipped (#766): reusing an existing acceptance source is no longer a flag — every
`*-fast-loop.sh` harness now resolves a stable source by name and adds a version to it,
falling back to creation only on the first run. Minting one per run also minted a document
per run, which inflated `search_hits` — an ADR-0030 gate — by counting one law twice.

Definition of done:

- operator can rerun the same template without editing the script

#### Task 2.3: Persist evidence locally

Goal:

- make each run inspectable after failure

Persist at minimum:

- `create.json`
- `readiness.json`
- `approve.json`
- `run-create.json`
- `run-state.json`
- `provider-jobs.json`
- `preview-summary.json`
- `captured-resources.json`
- `raw-artifacts.json`
- `processing-status.json`
- `document-lifecycle.json`

Definition of done:

- every loop execution writes a timestamped bundle under a predictable temp path

### Track 3: machine-checkable gates

#### Task 3.1: Add acquisition gates

The loop must fail unless:

- run reaches `completed`
- at least one provider job exists
- provider job status is `completed`
- captured resources count is greater than zero
- raw artifacts count is greater than zero
- content type includes `text/html`

#### Task 3.2: Add downstream gates

The loop must fail unless processing includes:

- `accepted`
- `processing`
- `canonical_ready`

The loop must fail unless lifecycle includes:

- `document.processed`

#### Task 3.3: Add minimum content gates

The loop must fail unless:

- title contains `Bundesverfassung`
- final URL points at a Fedlex filestore HTML manifestation
- fetched content contains `Art. 1`

Definition of done:

- the loop returns a useful verdict, not just raw JSON

Suggested verdicts:

- `pass`
- `pipeline_pass_content_suspect`
- `provider_failed`
- `downstream_failed`

### Track 4: local provider smoke

#### Task 4.1: Add a real Fedlex provider smoke

Goal:

- catch provider regressions before Cloud Run deploy

Smoke responsibilities:

- resolve work URI -> expression URI
- resolve expression URI -> manifestation URL
- fetch manifestation HTML
- assert body contains `Art. 1`

Definition of done:

- explicit local test or smoke command runs against the real Fedlex surface

#### Task 4.2: Add a metadata fixture snapshot

Capture at minimum:

- title
- short title
- final URL pattern
- preferred language

Definition of done:

- provider output shape regressions are visible in a narrow diff

### Track 5: narrow CH expansion

#### Task 5.1: Add one more narrow CH template

Goal:

- prove the path is not constitution-only

Constraints:

- one known federal law
- German first
- one work URI

Definition of done:

- second CH template passes the same fast loop

#### Task 5.2: Add a tiny bounded batch

Goal:

- test small-batch stability before any broadening

Constraints:

- `max_resources=5`
- no broad discovery
- no homepage roots

Definition of done:

- five-resource preview passes acquisition, DI, lifecycle, and minimal content gates

### Track 6: runner and deploy reliability

#### Task 6.1: Fix heavy runner label churn

Goal:

- keep both heavy runners schedulable

Definition of done:

- heavy runners remain labeled through rotation
- image jobs no longer starve on a single usable runner

#### Task 6.2: Fix runner egress for image builds

Observed failures:

- `docker.io` BuildKit bootstrap pull
- `docker.pkg.dev` push during `platform-control` image export

Goal:

- eliminate manual registry-copy workarounds

Definition of done:

- image build and Artifact Registry push succeed repeatedly from self-hosted heavy runners

#### Task 6.3: Add an image-push preflight

Check at minimum:

- Buildx bootstrap
- `docker.io` reachability
- Artifact Registry push reachability

Definition of done:

- runner failures are caught before long runtime image workflows are dispatched

### Track 7: Temporal preparation after loop stability

#### Task 7.1: Design Temporal around the proven run path

Temporal should own:

- shard enumeration
- run fan-out
- retry failed shards
- checkpointing
- backfills

Temporal should not replace:

- provider logic
- expression resolution
- manifestation fetch

Definition of done:

- one design note maps `Temporal -> platform-control run -> fedlex_sparql provider -> DI`

#### Task 7.2: Delay Temporal implementation until the fast loop is stable

Rule:

- do not add orchestration while the narrow slice still depends on manual deploy workarounds

## Recommended execution order

1. Task 1.1 — `platform-control-only` image workflow
2. Task 1.2 — `platform-control-only` dev deploy workflow
3. Task 2.1 — `scripts/ch-fedlex-fast-loop.sh`
4. Task 3.1-3.3 — machine-checkable gates
5. Task 4.1-4.2 — local provider smoke
6. Task 5.1 — second narrow CH template
7. Task 5.2 — five-resource batch
8. Task 6.1-6.3 — runner reliability hardening
9. Task 7.1-7.2 — Temporal preparation

## Near-term autonomous loop target

We should consider the fast loop ready when this is true:

- one command deploys `platform-control-api-dev`
- one command runs the narrow CH preview
- the loop checks `text/html`, `canonical_ready`, and `document.processed`
- the loop checks a minimal legal-text signal like `Art. 1`
- total operator time is under 10 minutes
- failure output is specific enough to tell whether the problem is:
  - provider resolution
  - manifestation fetch
  - DI handoff
  - lifecycle/projection
  - deploy or runner infrastructure

## Suggested ticket titles

Use these if we split the work into separate issues:

1. `Add platform-control-only runtime image workflow`
2. `Add platform-control-only dev deploy workflow`
3. `Add CH Fedlex fast-loop smoke command`
4. `Add machine-checkable CH acquisition and DI gates`
5. `Add local Fedlex manifestation smoke`
6. `Add second narrow CH Fedlex template`
7. `Stabilize heavy runner labels and image-push egress`
8. `Design Temporal shard and backfill flow for CH Fedlex`
