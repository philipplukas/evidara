# 2026-04-14 AT RIS Fast Loop Template

Owner: Platform / GA
Environment: dev  
Purpose: ready-to-fill evidence packet for the AT narrow rerun and AT tiny batch rerun once the
patched API + worker deploy is live

## Live prereqs

- `platform-control-api-dev` deployed to the patched branch SHA
- `platform-control-worker-dev` deployed to the patched branch SHA
- AT fast loop script:
  - [scripts/at-ris-fast-loop.sh](../../../scripts/at-ris-fast-loop.sh)

## Narrow rerun

- Template: `ris_ogd_bundesrecht_narrow_html`
- Jurisdiction ID: `jur_at_federal`
- Authority ID: `auth_ris` or auto-resolved live equivalent
- Command:

```bash
EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT='gha-deployer-staging@project-dacd6b7b-dc96-4534-b82.iam.gserviceaccount.com' \
EVIDARA_PLATFORM_CONTROL_URL='https://platform-control-api-dev-kxc5agexna-oa.a.run.app' \
EVIDARA_LEGAL_SEARCH_URL='https://legal-search-api-dev-kxc5agexna-oa.a.run.app' \
bash /Users/philipp/Work/Tart/evidara/scripts/at-ris-fast-loop.sh --json --template ris_ogd_bundesrecht_narrow_html
```

- Run ID: `<fill>`
- Source ID: `<fill>`
- Source version ID: `<fill>`
- Run dir: `<fill>`
- Verdict: `<pass|pipeline_pass_content_suspect|provider_failed|downstream_failed>`

### Checks

- captured_count: `<fill>`
- raw_artifact_count: `<fill>`
- content_type_html_count: `<fill>`
- accepted_count: `<fill>`
- processing_count: `<fill>`
- canonical_ready_count: `<fill>`
- processed_count: `<fill>`
- title_ok: `<fill>`
- ris_html_ok: `<fill>`
- section_gate_ok: `<fill>`

### Notes

- upstream RIS timeout / latency symptoms: `<fill>`
- operator judgment: `<fill>`

## Tiny batch rerun

- Template: `ris_ogd_bundesrecht_small_batch_html`
- Max resources: `5`
- Command:

```bash
EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT='gha-deployer-staging@project-dacd6b7b-dc96-4534-b82.iam.gserviceaccount.com' \
EVIDARA_PLATFORM_CONTROL_URL='https://platform-control-api-dev-kxc5agexna-oa.a.run.app' \
EVIDARA_LEGAL_SEARCH_URL='https://legal-search-api-dev-kxc5agexna-oa.a.run.app' \
bash /Users/philipp/Work/Tart/evidara/scripts/at-ris-fast-loop.sh --json --template ris_ogd_bundesrecht_small_batch_html --max-resources 5
```

- Run ID: `<fill>`
- Source ID: `<fill>`
- Source version ID: `<fill>`
- Run dir: `<fill>`
- Verdict: `<pass|pipeline_pass_content_suspect|provider_failed|downstream_failed>`

### Checks

- captured_count: `<fill>`
- raw_artifact_count: `<fill>`
- content_type_html_count: `<fill>`
- accepted_count: `<fill>`
- processing_count: `<fill>`
- canonical_ready_count: `<fill>`
- processed_count: `<fill>`
- title_ok: `<fill>`
- ris_html_ok: `<fill>`
- section_gate_ok: `<fill>`

### Notes

- any duplicate/quality drift across batch items: `<fill>`
- operator judgment: `<fill>`

## TAR-239 / TAR-160 paste block

> AT RIS fast loop rerun complete on dev.
> Narrow result: `<verdict>` (`<run_id>`).
> Tiny batch result: `<verdict>` (`<run_id>`).
> Evidence: HTML capture, DI `accepted -> processing -> canonical_ready`, lifecycle
> `document.processed`, plus AT title / section quality gates.
> Remaining gaps: `<fill or none>`.
