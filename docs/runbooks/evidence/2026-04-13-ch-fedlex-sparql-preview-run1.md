# 2026-04-13 CH Fedlex SPARQL Preview Run 1

Owner: Platform / GA  
Environment: `dev`  
Executed at: `2026-04-13T19:39:08Z` to `2026-04-13T19:39:29Z`  
Status: completed with `config-change-needed` judgment

## Summary

This was the first live CH preview run against the new deterministic `fedlex_sparql` provider on
`platform-control` dev.

The run succeeded technically end to end:

- Cloud Run auth bootstrap succeeded
- source + source version creation succeeded
- readiness returned `ready=true`
- version approval succeeded
- bounded preview run completed
- provider job completed
- raw artifact was written
- `artifact_bundle.available` reached `di-consumer-dev` with HTTP `200`
- DI published `accepted`, `processing`, and `canonical_ready`
- `document.processed` reached `platform-control-api-dev`

The first operator check happened too early and showed empty processing/lifecycle rows. That was an
observability timing issue, not a DI compatibility failure. The rows appeared about `19s` after the
run completed.

The remaining blocker is content shape, not transport:

- the provider currently emits a JSON metadata bundle with embedded Turtle
- DI accepts and processes that bundle
- but the artifact is not yet a text-bearing Swiss law document suitable for final CH production

## Canonical live inputs

- `jurisdiction_id=jur_ch_federal`
- `authority_id=auth_fedlex`
- `overlay_id=ch`
- `provider_template_id=fedlex_sparql_constitution_de`

## Source and source version

Created source:

- `source_id=src_01kp45npzvrjym8011j28v94sr`
- `name=CH Fedlex SPARQL constitution thin slice`
- `jurisdiction_id=jur_ch_federal`
- `authority_id=auth_fedlex`

Created source version:

- `source_version_id=sv_01kp45nq0s77e5wxmf5457eeny`
- `status=draft`, then `approved`
- `provider=fedlex_sparql`

## Readiness

Readiness result:

- `ready=true`

Checks included:

- `source_exists` -> ok
- `source_version_exists` -> ok
- `source_version_belongs_to_source` -> ok
- `mode_compatible_with_version_status` -> ok
- `acquisition_seed_present` -> ok

## Run

Run request:

- `mode=preview`
- `scope.kind=discovered_subset`
- `scope.max_resources=25`

Created run:

- `run_id=run_01kp45nqjb0n0eex3dkdt7w3jv`
- `status=completed`

## Provider job

Provider job:

- `provider_job_id=pjob_01kp45nqyr20pmefga7zeazbe2`
- `provider=fedlex_sparql`
- `status=completed`
- `last_event_type=inline.completed`

Request payload:

- `work_uris=["https://fedlex.data.admin.ch/eli/cc/1999/404"]`
- `sparql_endpoint="https://fedlex.data.admin.ch/sparqlendpoint"`
- `preferred_languages=["de"]`
- `max_expressions=1`

Response payload:

- `requested=1`
- `captured=1`
- `failed=0`

## Captured resource and artifact

Captured resource:

- `captured_resource_id=cap_01kp45nr8dndgqjtkmz1wmmx4d`
- `source_url=https://fedlex.data.admin.ch/eli/cc/1999/404`
- `final_url=https://fedlex.data.admin.ch/eli/cc/1999/404`
- `title=Bundesverfassung der Schweizerischen Eidgenossenschaft vom 18. April 1999`
- `content_type=application/json`
- `http_status=200`
- `discovery_depth=0`

Raw artifact:

- `artifact_id=art_01kp45nqy1s6b9x5dsp80sb5j7`
- `storage_path=gs://evidara-raw-artifacts-dev/runs/run_01kp45nqjb0n0eex3dkdt7w3jv/art_01kp45nqy1s6b9x5dsp80sb5j7.json`

Artifact payload facts:

- `work_uri=https://fedlex.data.admin.ch/eli/cc/1999/404`
- selected expression URI:
  - `https://fedlex.data.admin.ch/eli/cc/1999/404/de`
- `title_short=BV`
- payload includes `describe_turtle`

## Downstream handoff

Ingress:

- `di-consumer-dev` received `POST /internal/events/artifact-bundles:process` with HTTP `200` at
  `2026-04-13T19:39:15.326Z`

Outbound DI events recorded by `platform-control-api-dev`:

- `document.processing_status.updated` -> `accepted`
- `document.processing_status.updated` -> `processing`
- `document.processing_status.updated` -> `canonical_ready`
- `document.processed` -> `lifecycle_status=active`

Observed processing rows:

- `processing_manifest_id=pm_5a0gf3dtfp8nja62fvsrfnz9v0`
- `document_id=doc_1wxstrwdxtwh0zaxag6x37hya2`
- `document_revision=1`
- `processing_version=0.1.0-dev`

Observed lifecycle row:

- `event_type=document.processed`
- `lifecycle_status=active`
- `document_id=doc_1wxstrwdxtwh0zaxag6x37hya2`

## Important operator note

The first manual fetch of:

- `/v1/runs/{run_id}/processing-status`
- `/v1/runs/{run_id}/document-lifecycle`

returned empty arrays because it happened before the Pub/Sub round-trip completed. For this path,
operators should wait roughly `20-30s` after run completion before concluding downstream DI is
missing.

## Judgment

Technical outcome:

- acquisition path works
- bundle publication works
- DI ingestion works
- status/lifecycle callbacks work

Remaining issue:

- the current `fedlex_sparql` provider emits metadata-plus-Turtle JSON, not a text-bearing law
  artifact

Classification:

- not a DI blocker
- not a callback blocker
- not a platform transport blocker
- `config-change-needed`
- subtype: provider output needs text-bearing manifestation or canonical text extraction step

## Recommended next move

Do not debug Pub/Sub or DI for this path further.

Instead:

1. keep `fedlex_sparql` as the deterministic discovery/resolution layer
2. evolve the provider to resolve and emit a text-bearing manifestation or canonical text payload
3. rerun the same bounded CH preview once the provider emits law text rather than metadata-only JSON
