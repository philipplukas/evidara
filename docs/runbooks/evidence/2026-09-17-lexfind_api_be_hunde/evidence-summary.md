# CH LexFind BE Fast Loop Evidence Summary

- Environment: `dev`
- Template: `lexfind_api_be_hunde`
- Source: `src_01m2r0x8qhkdz9zvymf1zt7sqd`
- Source version: `sv_01m2r0x8qk7pn1k1bvvhspc19c`
- Run: `run_01m2r0x94x7sjqct58rs9tnbdk`
- Verdict: `pass`
- Max resources: `10`
- Run mode: `acceptance`
- Started at (UTC): `2026-09-17T15:49:03Z`
- Completed at (UTC): `2026-09-17T15:49:33Z`
- Run dir: `/tmp/claude-1000/-home-philipp-Projects-evidara/7bf473c8-0299-4d12-bc66-c25e7b989375/scratchpad/evidence/lexfind_be_hunde`
- Jurisdiction: `jur_ch_be`
- Authority: `auth_be_sk`

## Gate coverage

- `body_lang_hint_ok` — **excluded** (`not_a_german_template`): deliberately not asserted for this corpus, so it is unverified but not a hole.

## Checks

- `captured_count=2`
- `raw_artifact_count=2`
- `expect_content_type=application/pdf`
- `content_type_match_count=2`
- `url_pattern=lexfind\.ch/`
- `accepted_count=2`
- `processing_count=2`
- `canonical_ready_count=2`
- `processed_count=1`
- `title_ok=2`
- `title_checked=1`
- `indexed_title_ok=1`
- `indexed_title_checked=1`
- `indexed_title_observed=doc_193ktma5ewqws5zwbmsmyzj1bs=Hundegesetz`
- `url_pattern_ok=2`
- `art1_ok=1`
- `art_density_count=28`
- `art_density_ok=1`
- `content_gate_source=canonical`
- `body_max_length=9641`
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
- `indexed_language_observed=doc_193ktma5ewqws5zwbmsmyzj1bs=de`
- `indexed_language_checked=1`
- `indexed_language_ok=1`
- `as_of_utc=2026-09-17`
- `in_force_from_present=2`
- `future_dated_count=0`
- `not_in_force_count=0`
- `in_force_ok=1`

## TAR-239 / TAR-160 Paste Block

> CH LexFind BE fast loop `lexfind_api_be_hunde` on `dev` returned `pass` (`run_01m2r0x94x7sjqct58rs9tnbdk`).
> Checks: captured=`2`, raw_artifacts=`2`, application/pdf=`2`, DI accepted/processing/canonical_ready=`2/2/2`, lifecycle processed=`1`.
> Run mode: `acceptance` — an acceptance rehearsal, not production ingest; it does not imply either ADR-0030 key is turned.
> Gates excluded (not applicable, not asserted): `body_lang_hint_ok`.
> Gates NOT EVALUATED (asked for, could not run): none.
> Source/version: `src_01m2r0x8qhkdz9zvymf1zt7sqd` / `sv_01m2r0x8qk7pn1k1bvvhspc19c`.
> Next action: Attach this block to TAR-239 and roll the judgment into TAR-160.
