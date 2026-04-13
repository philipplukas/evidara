# 2026-04-13 CH Fedlex Thin Slice Run 1

Owner: Platform / GA  
Environment: `dev`  
Executed at: `2026-04-13T15:52:55Z` to `2026-04-13T15:53:19Z`  
Status: completed with `config-change-needed` judgment

## Summary

This was the first live CH deterministic thin slice against the `platform-control` dev API.
The run succeeded technically end to end:

- Cloud Run auth bootstrap succeeded
- blueprint preview succeeded
- source + source version creation succeeded
- readiness returned `ready=true`
- version approval succeeded
- bounded preview run completed
- provider job completed
- raw artifact was written
- downstream processing status and document lifecycle rows were emitted

The content result was not clean enough to widen. The deterministic Fedlex blueprint captured only
the Fedlex homepage shell, not a concrete legislation page. This is a configuration-quality issue,
not a platform reliability issue.

## Canonical live inputs

The original CH slice plan assumed:

- `jurisdiction_id=jur_ch`
- `authority_id=auth_ch_fedlex`

The live dev hierarchy required the stricter federal pair:

- `jurisdiction_id=jur_ch_federal`
- `authority_id=auth_fedlex`

This drift should be treated as a documented CH authority-mapping mismatch, not hidden.

## Reference-data findings

Timestamp: `2026-04-13T15:52:55Z`

Existing jurisdiction rows included:

- `jur_ch`
- `jur_ch_federal`

Existing authority rows included:

- `auth_fedlex` on `jur_ch_federal`
- `auth_bger` on `jur_ch_federal`

Observed blocker:

- `auth_ch_fedlex` did not exist in the live API response
- the running service hierarchy and tests align on `auth_fedlex`, not `auth_ch_fedlex`

Classification:

- `reference-data blocker`
- `CH-specific mapping blocker`
- subtype: authority naming inconsistency

## Blueprint preview

Request:

- `overlay_id=ch`
- `provider_template_id=deterministic_http_fedlex_legislation`

Observed result:

- `provider=deterministic_http`
- `seed_urls=["https://www.fedlex.admin.ch/"]`
- `document_type_hint=legislation`

Judgment:

- blueprint expansion is valid
- no template drift detected

## Source and source version

Created source:

- `source_id=src_01kp3rqfrcgz9xyac90t3h71cr`
- `name=CH Fedlex legislation thin slice 20260413T155255Z`
- `jurisdiction_id=jur_ch_federal`
- `authority_id=auth_fedlex`

Created source version:

- `source_version_id=sv_01kp3rqfs85fy2cpz21yx9qzjz`
- `version_label=ch-fedlex-v1-20260413T155255Z`
- `status=draft`, then `approved`
- provider `deterministic_http`

## Readiness

Readiness request:

- `source_id=src_01kp3rqfrcgz9xyac90t3h71cr`
- `source_version_id=sv_01kp3rqfs85fy2cpz21yx9qzjz`
- `mode=preview`

Readiness result:

- `ready=true`

Checks:

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

- `run_id=run_01kp3rqx5nw6gyyrtnzcy48z3y`
- `status=completed`
- `started_at=2026-04-13T15:53:09.691021Z`
- `completed_at=2026-04-13T15:53:10.393905Z`

## Provider job

Provider job:

- `provider_job_id=pjob_01kp3rqxd5aw8d4t7gvvtx2qk5`
- `provider=deterministic_http`
- `external_job_id=dethttp_run_01kp3rqx5nw6gyyrtnzcy48z3y`
- `status=completed`
- `last_event_type=inline.completed`

Request payload:

- `seed_urls=["https://www.fedlex.admin.ch/"]`
- `timeout_seconds=30`
- `max_content_bytes=2000000`

Response payload:

- `requested=1`
- `captured=1`
- `failed=0`

## Preview summary

Preview summary:

- `captured_url_count=1`
- `artifacts_count=1`
- `captured_resources_count=1`
- `pdf_count=0`
- `likely_decision_page_count=0`
- `likely_boilerplate_page_count=0`
- `likely_duplicate_page_count=0`
- content type breakdown:
  - `text/html=1`

Drift checks:

- `artifact-count` -> ok
- `captured-resource-count` -> ok
- `content-types-known` -> ok

## Captured resource and artifact

Captured resource:

- `captured_resource_id=cap_01kp3rqxmhwv363742x7xzv04t`
- `source_url=https://www.fedlex.admin.ch/`
- `final_url=https://www.fedlex.admin.ch/`
- `title=Fedlex`
- `content_type=text/html`
- `http_status=200`
- `discovery_depth=0`

Raw artifact:

- `artifact_id=art_01kp3rqx9w8w6da3d93hjyefyk`
- `storage_path=gs://evidara-raw-artifacts-dev/runs/run_01kp3rqx5nw6gyyrtnzcy48z3y/art_01kp3rqx9w8w6da3d93hjyefyk.json`

Important quality finding:

- the inline HTML body is the Fedlex homepage application shell
- it is not yet a concrete Swiss federal legislation page

Classification:

- `preview-quality blocker`
- subtype: homepage shell captured instead of legislation document

## Downstream processing

Processing status rows:

- `accepted`
- `processing`
- `canonical_ready`

Sample downstream row:

- `processing_manifest_id=pm_5j2w0577m29v4s3zh5fr2bhvjt`
- `document_id=doc_3eyevjm6agy450ctr7mm27yqm3`
- `document_revision=1`
- `processing_version=0.1.0-dev`

Document lifecycle row:

- `event_type=document.processed`
- `lifecycle_status=active`
- `document_id=doc_3eyevjm6agy450ctr7mm27yqm3`
- `processing_manifest_id=pm_5j2w0577m29v4s3zh5fr2bhvjt`

Judgment:

- no downstream DI blocker
- no callback/artifact blocker
- no platform execution blocker

## Retry decision

Do not retry this run as-is.

Reason:

- this is not a transient provider or callback failure
- the run completed cleanly
- the problem is acquisition quality, not platform instability

Retry class:

- `not retryable without config change`

## Final operator judgment

Judgment: `config-change-needed`

Why:

- the deterministic Fedlex slice is operationally valid
- the current blueprint seed fetches only the Fedlex homepage shell
- widening this configuration would likely amplify low-value captures rather than improve coverage

## Recommended next actions

1. Keep deterministic CH first, but tighten the acquisition config to specific legislation landing
   URLs rather than the Fedlex homepage root.
2. If stable legislation landing URLs are not obvious, use a small AI-assisted discovery pass only
   to identify Fedlex legislation entry paths, then convert the result back into a reviewed
   deterministic config.
3. Do not promote this exact blueprint/config to production yet.
4. Attach this evidence note to the CH/AT lane (`TAR-239`) and summarize it in `TAR-160`.

## Follow-up: SPARQL-backed metadata finding

Additional live probing after this run showed that `fedlex.data.admin.ch` exposes a public
SPARQL endpoint:

- `https://fedlex.data.admin.ch/sparqlendpoint`

Confirmed deterministic query results:

- querying `<https://fedlex.data.admin.ch/eli/cc/1999/404>` returned RDF graph rows
- querying `jolux:isRealizedBy` on that work returned expression URIs:
  - `https://fedlex.data.admin.ch/eli/cc/1999/404/de`
  - `https://fedlex.data.admin.ch/eli/cc/1999/404/fr`
  - `https://fedlex.data.admin.ch/eli/cc/1999/404/it`
  - `https://fedlex.data.admin.ch/eli/cc/1999/404/en`
  - `https://fedlex.data.admin.ch/eli/cc/1999/404/rm`

Important interpretation:

- Fedlex metadata is available deterministically through SPARQL
- the browser metadata page is backed by `POST /api/public/namedsparql/metadata/group/type`
- raw GET fetches of the Fedlex web/document URLs still return either SPA shells or `400` errors

Implication:

- CH can likely keep a deterministic discovery layer, but not via the current
  `deterministic_http` homepage-root blueprint
- the better deterministic path is likely an API-aware CH provider or a reviewed SPARQL-backed
  resolution step
- until that exists, the smallest practical next experiment is a narrow JS-capable / AI-assisted
  discovery slice against known Fedlex metadata URLs
