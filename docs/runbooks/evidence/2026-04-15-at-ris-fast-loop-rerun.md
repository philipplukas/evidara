# 2026-04-15 AT RIS Fast Loop Rerun

Owner: Platform / GA
Environment: `dev`
Executed at: `2026-04-15T10:19:28Z` to `2026-04-15T10:20:03Z`
Status: completed with `pass` judgment

## Summary

This note captures the AT RIS fast-loop rerun after the live worker-backed dispatch fix and the
`di-consumer-dev` redeploy from image tag `53550174e5b4454ec0a5b9e86178ec7510444aa2`
(`di-consumer-dev-00011-6kp`).

The runtime path is healthy again on `dev`: the worker-backed replay path passes, DI publishes the
expected downstream signals, and `document.processed` is recorded. The residual user-visible gap is
still title quality for the AT proof doc in legal-search: `doc_7m5fzs4ksj057ft0sgzqaecpyh` still
returns `RIS Dokument`.

## Canonical live inputs

- `jurisdiction_id=jur_at_federal`
- `authority_id=auth_ris`
- `template_id=ris_ogd_bundesrecht_small_batch_html`

## Run

Source:

- `source_id=src_01kp8aejxr5wj2jnhtg3t80wsz`
- `source_version_id=sv_01kp8aejyk596n2jkrmcmhbrkv`

Run:

- `run_id=run_01kp8aek9590wsaas3patxbct7`
- `status=completed`
- `verdict=pass`

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

## Post-rerun document check

Direct legal-search detail check after the rerun:

- `document_id=doc_7m5fzs4ksj057ft0sgzqaecpyh`
- `title=RIS Dokument`
- `document_type=null`
- subtitle still renders as `Schweiz · Gesetz · Rechtsinformationssystem des Bundes`

Interpretation:

- runtime blocker: fixed
- worker-backed replay path: fixed
- AT proof-doc title cleanup: still open
- broader relevance/ranking: not re-evaluated by this note

## Judgment

Classification:

- runtime parity / dispatch: `pass`
- AT fast-loop replay path: `pass`
- AT proof-doc title quality: `open`

This supersedes the 2026-04-14 AT fast-loop note as the latest runtime-path proof for `dev`,
while keeping the 2026-04-14 note as the original recovery record.
