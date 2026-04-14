# Platform-Control Provider Canary

Owner: Platform / deploy canary lane  
Last reviewed: 2026-04-14  
Last verified: 2026-04-14  
Applies to: `platform-control` fast deploy follow-up on `dev`

## Purpose

Run one narrow post-deploy canary that proves more than health and readiness.

This workflow verifies the full provider path for a single CH or AT slice:

1. create source + source version
2. readiness check
3. approve version
4. create preview run
5. acquisition completes
6. DI reaches `accepted`, `processing`, and `canonical_ready`
7. lifecycle emits `document.processed`

Use this when a `platform-control` deploy is supposed to change provider behavior, run dispatch,
or artifact handoff, and we want one runtime-native confidence check before widening further.

## Workflow

- GitHub Actions workflow: `.github/workflows/platform-control-provider-canary.yml`
- Trigger: `workflow_dispatch`
- Intended follow-up to:
  - `.github/workflows/platform-control-fast-deploy.yml`
- Related local operator loops:
  - [`scripts/ch-fedlex-fast-loop.sh`](../../scripts/ch-fedlex-fast-loop.sh)
  - [`scripts/at-ris-fast-loop.sh`](../../scripts/at-ris-fast-loop.sh)

## When to use this workflow

Use the provider canary when:

- a deploy changed `platform-control` provider logic
- a deploy changed run dispatch behavior
- a deploy changed worker/API artifact or event wiring
- we want a CI-native post-deploy proof without relying on a local laptop session

Do not use it as a replacement for the local CH/AT fast loops during active iteration. The local
scripts are still the fastest operator path for repeated provider tuning. This workflow is the
post-deploy check that proves the deployed Cloud Run service behaves the same way.

## Supported canaries

### `corpus=ch`

Default template:

- `fedlex_sparql_constitution_de`

Expected proof shape:

- `text/html` artifact capture
- Fedlex filestore HTML final URL
- `Art. 1` present in the captured body
- DI and lifecycle rows present

### `corpus=at`

Default template:

- `ris_ogd_bundesrecht_narrow_html`

Expected proof shape:

- `text/html` artifact capture
- RIS Bundesnormen HTML final URL
- section/article signal present (`§ 1` or `Art. 1`)
- DI and lifecycle rows present

## Inputs

- `environment`
  - currently `dev`
- `corpus`
  - `ch` or `at`
- `template`
  - optional override when we want to run a non-default narrow template
- `max_resources`
  - optional preview-scope override
- `max_polls`
  - run polling budget before timeout
- `poll_interval`
  - seconds between run polls
- `upload_artifact`
  - whether to retain the evidence bundle as a workflow artifact

## Outputs and artifacts

The workflow always writes a narrow evidence bundle and uploads it as a GitHub artifact when
`upload_artifact=true`.

The bundle includes:

- `platform-control-health.json`
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
- `summary.json`
- `evidence-snippet.md`

## Verdicts

The workflow surfaces the same practical verdict categories we use in the local fast loops:

- `pass`
  - acquisition, DI, lifecycle, and minimum content checks all passed
- `provider_failed`
  - run completed or failed without a usable HTML artifact set
- `downstream_failed`
  - acquisition completed, but DI/lifecycle proof did not show up
- `pipeline_pass_content_suspect`
  - transport succeeded, but the captured content does not look trustworthy enough
- `workflow_error`
  - the canary itself failed before it could produce a normal verdict

## Recommended operator pattern

1. Run `platform-control-fast-deploy`.
2. Run `platform-control-provider-canary` for the affected corpus.
3. If the canary passes, continue with wider local/operator validation.
4. If it fails:
   - inspect the uploaded evidence bundle first
   - use the verdict to decide whether this is provider, downstream, or quality work
   - only then widen or update evidence tickets

## Limits

This canary proves `platform-control` create-run to DI/lifecycle behavior. It does not replace:

- search/detail smoke in `legal-search`
- full GA evidence assembly
- broader multi-resource acceptance runs
- local provider iteration loops

## Related

- [CH + AT Thin-Slice Execution](ch-at-thin-slice-execution.md)
- [CH Fedlex Fast-Loop Backlog](ch-fedlex-fast-loop-backlog.md)
- [Friction and Acceleration Map](friction-and-acceleration-map.md)
