# CH Stadt Zürich Fast Loop Evidence Summary

- Environment: `dev`
- Template: `gemeinde_http_zh_stadt_hundevorschriften`
- Source: `src_01m2r07ca78yqq7b9sb4r0w1xe`
- Source version: `sv_01m2r0dcqdnpzp31fp8z2sfdx0`
- Run: `run_01m2r0dd6nw0cxjt5b0krrt574`
- Verdict: `pass`
- Max resources: `10`
- Run mode: `acceptance`
- Started at (UTC): `2026-09-17T15:40:23Z`
- Completed at (UTC): `2026-09-17T15:40:47Z`
- Run dir: `/tmp/claude-1000/-home-philipp-Projects-evidara/7bf473c8-0299-4d12-bc66-c25e7b989375/scratchpad/evidence/gemeinde_zh3`
- Jurisdiction: `jur_ch_gemeinde_261`
- Authority: `auth_stadt_zuerich_sk`

## Gate coverage

- `body_lang_hint_ok` — **excluded** (`not_a_german_template`): deliberately not asserted for this corpus, so it is unverified but not a hole.

## Checks

- `captured_count=1`
- `raw_artifact_count=1`
- `expect_content_type=application/pdf`
- `content_type_match_count=1`
- `url_pattern=stadt-zuerich\.ch/`
- `accepted_count=1`
- `processing_count=1`
- `canonical_ready_count=1`
- `processed_count=1`
- `title_ok=1`
- `title_checked=1`
- `indexed_title_ok=1`
- `indexed_title_checked=1`
- `indexed_title_observed=doc_4mkn0yt4bnd4zh9qz9w2ag10qw=Vollzugsvorschriften zum Hundegesetz`
- `url_pattern_ok=1`
- `art1_ok=1`
- `art_density_count=8`
- `art_density_ok=1`
- `content_gate_source=canonical`
- `body_max_length=3080`
- `min_content_length_ok=1`
- `min_content_length_floor=2048`
- `lang_agreement_ok=1`
- `body_lang_hint_ok=1`
- `body_lang_hint_checked=0`
- `skipped_gates=["body_lang_hint_ok"]`
- `gate_coverage=[{"gate":"body_lang_hint_ok","outcome":"excluded","reason":"not_a_german_template"}]`
- `excluded_gates=["body_lang_hint_ok"]`
- `not_evaluated_gates=[]`
- `indexed_language_expected=de`
- `indexed_language_observed=doc_4mkn0yt4bnd4zh9qz9w2ag10qw=de`
- `indexed_language_checked=1`
- `indexed_language_ok=1`
- `as_of_utc=2026-09-17`
- `in_force_from_present=1`
- `future_dated_count=0`
- `not_in_force_count=0`
- `in_force_ok=1`

## TAR-239 / TAR-160 Paste Block

> CH Stadt Zürich fast loop `gemeinde_http_zh_stadt_hundevorschriften` on `dev` returned `pass` (`run_01m2r0dd6nw0cxjt5b0krrt574`).
> Checks: captured=`1`, raw_artifacts=`1`, application/pdf=`1`, DI accepted/processing/canonical_ready=`1/1/1`, lifecycle processed=`1`.
> Run mode: `acceptance` — an acceptance rehearsal, not production ingest; it does not imply either ADR-0030 key is turned.
> Gates excluded (not applicable, not asserted): `body_lang_hint_ok`.
> Gates NOT EVALUATED (asked for, could not run): none.
> Source/version: `src_01m2r07ca78yqq7b9sb4r0w1xe` / `sv_01m2r0dcqdnpzp31fp8z2sfdx0`.
> Next action: Attach this block to TAR-239 and roll the judgment into TAR-160.
