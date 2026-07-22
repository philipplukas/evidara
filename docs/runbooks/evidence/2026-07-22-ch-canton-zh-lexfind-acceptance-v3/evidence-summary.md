# CH Fedlex compose e2e Fast Loop Evidence Summary

- Environment: `compose-local`
- Template: `lexfind_api_zh_tierschutz`
- Source: `src_01ky4w6qj04487wgpz90ha6k08`
- Source version: `sv_01ky4w6qj087zwy74awkhpqfk5`
- Run: `run_01ky4w6qjyxz799796ny34m84a`
- Verdict: `pass`
- Max resources: `25`
- Run mode: `acceptance`
- Started at (UTC): `2026-07-22T12:18:30Z`
- Completed at (UTC): `2026-07-22T12:18:50Z`
- Run dir: `docs/runbooks/evidence/2026-07-22-ch-canton-zh-lexfind-acceptance-v3`
- Jurisdiction: `jur_ch_zh`
- Authority: `auth_zh_sk`

## Gate coverage

- None — every gate below was evaluated.

## Checks

- `captured_count=4`
- `raw_artifact_count=4`
- `expect_content_type=application/pdf`
- `content_type_match_count=4`
- `accepted_count=4`
- `processing_count=4`
- `canonical_ready_count=4`
- `processed_count=4`
- `title_ok=4`
- `title_checked=1`
- `indexed_title_ok=4`
- `indexed_title_checked=1`
- `indexed_title_expected_count=4`
- `indexed_title_observed=doc_33ewd6c0y01x1bs78vkfdhgrns=Hundeverordnung (HuV) 554.51,doc_373azp5m76ejjpz41n320jdfy8=Kantonales Tierschutzgesetz 554.1,doc_4kn1yha1t67x4gst6s018jv7w2=Kantonale Tierschutzverordnung (KTSchV) 554.11,doc_5yxxzrd668maqfdadj3nz8kk0k=Hundegesetz (HuG) 554.5`
- `skipped_gates=[]`
- `search_hits=9`
- `indexed_language_expected=de`
- `indexed_language_observed=doc_33ewd6c0y01x1bs78vkfdhgrns=de,doc_373azp5m76ejjpz41n320jdfy8=de,doc_4kn1yha1t67x4gst6s018jv7w2=de,doc_5yxxzrd668maqfdadj3nz8kk0k=de`
- `indexed_language_checked=1`
- `indexed_language_ok=1`

## TAR-239 / TAR-160 Paste Block

> CH Fedlex compose e2e fast loop `lexfind_api_zh_tierschutz` on `compose-local` returned `pass` (`run_01ky4w6qjyxz799796ny34m84a`).
> Checks: captured=`4`, raw_artifacts=`4`, application/pdf=`4`, DI accepted/processing/canonical_ready=`4/4/4`, lifecycle processed=`4`.
> Run mode: `acceptance` — an acceptance rehearsal, not production ingest; it does not imply either ADR-0030 key is turned.
> Skipped gates (not verified): none.
> Source/version: `src_01ky4w6qj04487wgpz90ha6k08` / `sv_01ky4w6qj087zwy74awkhpqfk5`.
> Next action: Attach this block to TAR-239 and roll the judgment into TAR-160.
