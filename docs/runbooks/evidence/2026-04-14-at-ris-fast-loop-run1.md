# 2026-04-14 AT RIS Fast Loop Run 1

Owner: Platform / GA
Environment: `dev`
Executed at: `2026-04-14T11:58:45Z` to `2026-04-14T12:01:08Z`
Status: completed with `pass` judgment

## Summary

This note captures the first clean end-to-end AT RIS fast-loop proof after moving RIS-backed runs
onto worker dispatch and restoring worker artifact-store / Pub/Sub parity with
`platform-control-api-dev`.

Two live preview runs now pass on `dev`:

- narrow AT law slice:
  - `run_id=run_01kp5xqgrfyqq2abez3r666d9h`
  - `template_id=ris_ogd_bundesrecht_narrow_html`
- tiny widened AT batch:
  - `run_id=run_01kp5xrqvh61xfdace1x9sqed1`
  - `template_id=ris_ogd_bundesrecht_small_batch_html`

Both runs proved:

- source + source-version creation succeeds
- readiness returns `ready=true`
- approval succeeds
- `POST /v1/runs` returns immediately with a `pending` run instead of hanging inline
- the worker picks up the run and completes RIS acquisition
- captured artifacts are `text/html`
- DI publishes `accepted`, `processing`, and `canonical_ready`
- `document.processed` is recorded with `lifecycle_status=active`

## Root cause and fix

The first live AT narrow rerun completed acquisition but stalled at the downstream checks:

- `processing-status` returned `[]`
- `document-lifecycle` returned `[]`

The actual break was not the `ris_ogd` provider. It was worker environment parity:

- `platform-control-api-dev` had:
  - `PLATFORM_CONTROL_ARTIFACT_STORE_BACKEND=gcs`
  - `PLATFORM_CONTROL_EVENT_PUBLISHER_BACKEND=pubsub`
  - raw artifact bucket and Pub/Sub topic env vars
- `platform-control-worker-dev` only had:
  - `PLATFORM_CONTROL_RUN_DISPATCH_BACKEND=worker`

Because of that mismatch, the worker wrote bundle manifests under `file:///app/.data/...`,
which `di-consumer-dev` could not read cross-service. The live fix was to add the missing GCS and
Pub/Sub env vars to `platform-control-worker-dev`, then rerun the loop.

## Canonical live inputs

- `jurisdiction_id=jur_at_federal`
- `authority_id=auth_ris`
- `overlay_id=at`
- templates:
  - `ris_ogd_bundesrecht_narrow_html`
  - `ris_ogd_bundesrecht_small_batch_html`

## Narrow run

Source:

- `source_id=src_01kp5xqgf1vdb1jpdzvan7nwwb`
- `source_version_id=sv_01kp5xqgf37n1jtr88m2jb52gq`

Run:

- `run_id=run_01kp5xqgrfyqq2abez3r666d9h`
- `status=completed`
- verdict: `pass`

Checks:

- `captured_count=20`
- `raw_artifact_count=20`
- `content_type_html_count=20`
- `accepted_count=1`
- `processing_count=1`
- `canonical_ready_count=1`
- `processed_count=1`
- `title_ok=3`
- `ris_html_ok=20`
- `section_gate_ok=20`

## Tiny batch run

Source:

- `source_id=src_01kp5xrqhg3c9eknkyawpap4jv`
- `source_version_id=sv_01kp5xrqhvx0wdh2m296g14eze`

Run:

- `run_id=run_01kp5xrqvh61xfdace1x9sqed1`
- `status=completed`
- verdict: `pass`

Checks:

- `captured_count=20`
- `raw_artifact_count=20`
- `content_type_html_count=20`
- `accepted_count=1`
- `processing_count=1`
- `canonical_ready_count=1`
- `processed_count=1`
- `title_ok=3`
- `ris_html_ok=20`
- `section_gate_ok=20`

Observed downstream records for the tiny batch:

- `document_id=doc_4wc4f1p5mh5ecyps5rw36ka4hp`
- `document_id=doc_7m5fzs4ksj057ft0sgzqaecpyh`
- `processing_manifest_id=pm_2pn6e5hh9a9s9v90w3n6wrapxg`
- `processing_manifest_id=pm_1yjqys0kh389hv0bps96xnw1g0`
- lifecycle:
  - `document.processed`
  - `lifecycle_status=active`

## Operational takeaways

- AT RIS should stay on the async worker-backed path.
- RIS fetches should fail fast at the provider level, but long-running content fetches should not
  block `POST /v1/runs`.
- The worker must share the same GCS artifact store and Pub/Sub bundle publication config as the
  API service whenever it owns acquisition dispatch.
- `auth_ris` is the correct live authority ID on dev; operator loops should not assume the older
  seed name `auth_at_ris`.

## Judgment

Classification:

- AT narrow slice: `pass`
- AT tiny widened batch: `pass`

This is now sufficient to count as live AT fast-loop evidence for `TAR-239` and the `TAR-160`
GA packet.
