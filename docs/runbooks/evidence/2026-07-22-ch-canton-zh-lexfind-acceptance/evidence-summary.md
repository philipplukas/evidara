# CH Fedlex compose e2e Fast Loop Evidence Summary

- Environment: `compose-local`
- Template: `lexfind_api_zh_tierschutz`
- Source: `src_01ky4vypq4svfv3dctx37t3svc`
- Source version: `sv_01ky4vypq5brdj7rk4a814s36j`
- Run: `run_01ky4vypr43n2ww19599yxexs2`
- Verdict: `pass`
- Max resources: `25`
- Run mode: `acceptance`
- Started at (UTC): `2026-07-22T12:14:07Z`
- Completed at (UTC): `2026-07-22T12:14:17Z`
- Run dir: `docs/runbooks/evidence/2026-07-22-ch-canton-zh-lexfind-acceptance`
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
- `processing_count=3`
- `canonical_ready_count=3`
- `processed_count=2`
- `title_ok=4`
- `title_checked=1`
- `indexed_title_ok=2`
- `indexed_title_checked=1`
- `indexed_title_expected_count=2`
- `indexed_title_observed=doc_1srkr1hd6xe0ta8a5yd8k118kc=Hundeverordnung (HuV) 554.51,doc_5zv5efjk0pqrygqp4bffv5b9k6=Hundegesetz (HuG) 554.5`
- `skipped_gates=[]`
- `search_hits=5`
- `indexed_language_expected=de`
- `indexed_language_observed=doc_1srkr1hd6xe0ta8a5yd8k118kc=de,doc_5zv5efjk0pqrygqp4bffv5b9k6=de`
- `indexed_language_checked=1`
- `indexed_language_ok=1`

## TAR-239 / TAR-160 Paste Block

> CH Fedlex compose e2e fast loop `lexfind_api_zh_tierschutz` on `compose-local` returned `pass` (`run_01ky4vypr43n2ww19599yxexs2`).
> Checks: captured=`4`, raw_artifacts=`4`, application/pdf=`4`, DI accepted/processing/canonical_ready=`4/3/3`, lifecycle processed=`2`.
> Run mode: `acceptance` — an acceptance rehearsal, not production ingest; it does not imply either ADR-0030 key is turned.
> Skipped gates (not verified): none.
> Source/version: `src_01ky4vypq4svfv3dctx37t3svc` / `sv_01ky4vypq5brdj7rk4a814s36j`.
> Next action: Attach this block to TAR-239 and roll the judgment into TAR-160.
