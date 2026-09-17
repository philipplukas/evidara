# CH Fedlex SR Fast Loop Evidence Summary

- Environment: `dev`
- Template: `fedlex_sparql_sr_full_de`
- Source: `src_01m2r3xf7nqhn1nfv02rarddw3`
- Source version: `sv_01m2r90b7v3e989g0z8rs682z8`
- Run: `run_01m2r90bnpqj133863kwmeba1t`
- Verdict: `pass`
- Max resources: `10`
- Run mode: `acceptance`
- Started at (UTC): `2026-09-17T18:10:33Z`
- Completed at (UTC): `2026-09-17T18:10:55Z`
- Run dir: `/tmp/claude-1000/-home-philipp-Projects-evidara/7bf473c8-0299-4d12-bc66-c25e7b989375/scratchpad/evidence/sr_full4`
- Jurisdiction: `jur_ch_federal`
- Authority: `auth_fedlex`

## Gate coverage

- `title_ok` — **excluded** (`no_expected_title_declared`): deliberately not asserted for this corpus, so it is unverified but not a hole.
- `indexed_title_ok` — **excluded** (`no_expected_title_declared`): deliberately not asserted for this corpus, so it is unverified but not a hole.

## Checks

- `captured_count=1`
- `raw_artifact_count=1`
- `expect_content_type=text/html`
- `content_type_match_count=1`
- `url_pattern=fedlex\.admin\.ch/filestore/.+\.html$`
- `accepted_count=1`
- `processing_count=1`
- `canonical_ready_count=1`
- `processed_count=1`
- `title_ok=1`
- `title_checked=0`
- `indexed_title_ok=1`
- `indexed_title_checked=0`
- `indexed_title_observed=doc_4czzb7zqt4q7jtssg9y4yyzbxw=Consolidation: 0.142.115.141 - 1875-01-29`
- `url_pattern_ok=1`
- `art1_ok=1`
- `art_density_count=8`
- `art_density_ok=1`
- `content_gate_source=canonical`
- `body_max_length=5350`
- `min_content_length_ok=1`
- `min_content_length_floor=2048`
- `lang_agreement_ok=1`
- `body_lang_hint_ok=1`
- `body_lang_hint_checked=1`
- `skipped_gates=["title_ok","indexed_title_ok"]`
- `gate_coverage=[{"gate":"title_ok","outcome":"excluded","reason":"no_expected_title_declared"},{"gate":"indexed_title_ok","outcome":"excluded","reason":"no_expected_title_declared"}]`
- `excluded_gates=["title_ok","indexed_title_ok"]`
- `not_evaluated_gates=[]`
- `indexed_language_expected=de`
- `indexed_language_observed=doc_4czzb7zqt4q7jtssg9y4yyzbxw=de`
- `indexed_language_checked=1`
- `indexed_language_ok=1`
- `as_of_utc=2026-09-17`
- `in_force_from_present=1`
- `future_dated_count=0`
- `not_in_force_count=0`
- `in_force_ok=1`

## TAR-239 / TAR-160 Paste Block

> CH Fedlex SR fast loop `fedlex_sparql_sr_full_de` on `dev` returned `pass` (`run_01m2r90bnpqj133863kwmeba1t`).
> Checks: captured=`1`, raw_artifacts=`1`, text/html=`1`, DI accepted/processing/canonical_ready=`1/1/1`, lifecycle processed=`1`.
> Run mode: `acceptance` — an acceptance rehearsal, not production ingest; it does not imply either ADR-0030 key is turned.
> Gates excluded (not applicable, not asserted): `title_ok`, `indexed_title_ok`.
> Gates NOT EVALUATED (asked for, could not run): none.
> Source/version: `src_01m2r3xf7nqhn1nfv02rarddw3` / `sv_01m2r90b7v3e989g0z8rs682z8`.
> Next action: Attach this block to TAR-239 and roll the judgment into TAR-160.
