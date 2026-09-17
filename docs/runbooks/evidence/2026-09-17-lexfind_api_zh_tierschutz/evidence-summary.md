# CH LexFind ZH Tierschutz Fast Loop Evidence Summary

- Environment: `dev`
- Template: `lexfind_api_zh_tierschutz`
- Source: `src_01m2q5fs0ytzrfa31drw12qqgj`
- Source version: `sv_01m2r0vejmq3y1hy5v94dry2p0`
- Run: `run_01m2r0vezyt2r0nvyf1m3yr1ym`
- Verdict: `pass`
- Max resources: `10`
- Run mode: `acceptance`
- Started at (UTC): `2026-09-17T15:48:04Z`
- Completed at (UTC): `2026-09-17T15:49:03Z`
- Run dir: `/tmp/claude-1000/-home-philipp-Projects-evidara/7bf473c8-0299-4d12-bc66-c25e7b989375/scratchpad/evidence/lexfind_zh_tierschutz`
- Jurisdiction: `jur_ch_zh`
- Authority: `auth_zh_sk`

## Gate coverage

- `body_lang_hint_ok` — **excluded** (`not_a_german_template`): deliberately not asserted for this corpus, so it is unverified but not a hole.

## Checks

- `captured_count=4`
- `raw_artifact_count=4`
- `expect_content_type=application/pdf`
- `content_type_match_count=4`
- `url_pattern=lexfind\.ch/`
- `accepted_count=4`
- `processing_count=4`
- `canonical_ready_count=4`
- `processed_count=3`
- `title_ok=4`
- `title_checked=1`
- `indexed_title_ok=1`
- `indexed_title_checked=1`
- `indexed_title_observed=doc_217x6752szaxg998ywend2ph69=Kantonale Tierschutzverordnung (KTSchV) 554.11,doc_3q9fx2qn5ecsg60ahd1425b60t=Hundeverordnung (HuV) 554.51,doc_3yb5vbat4sx5adr7s72z1y4k4j=Hundegesetz (HuG) 554.5`
- `url_pattern_ok=4`
- `art1_ok=2`
- `art_density_count=6`
- `art_density_ok=1`
- `content_gate_source=canonical`
- `body_max_length=24639`
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
- `indexed_language_observed=doc_217x6752szaxg998ywend2ph69=de,doc_3q9fx2qn5ecsg60ahd1425b60t=de,doc_3yb5vbat4sx5adr7s72z1y4k4j=de`
- `indexed_language_checked=1`
- `indexed_language_ok=1`
- `as_of_utc=2026-09-17`
- `in_force_from_present=4`
- `future_dated_count=0`
- `not_in_force_count=0`
- `in_force_ok=1`

## TAR-239 / TAR-160 Paste Block

> CH LexFind ZH Tierschutz fast loop `lexfind_api_zh_tierschutz` on `dev` returned `pass` (`run_01m2r0vezyt2r0nvyf1m3yr1ym`).
> Checks: captured=`4`, raw_artifacts=`4`, application/pdf=`4`, DI accepted/processing/canonical_ready=`4/4/4`, lifecycle processed=`3`.
> Run mode: `acceptance` — an acceptance rehearsal, not production ingest; it does not imply either ADR-0030 key is turned.
> Gates excluded (not applicable, not asserted): `body_lang_hint_ok`.
> Gates NOT EVALUATED (asked for, could not run): none.
> Source/version: `src_01m2q5fs0ytzrfa31drw12qqgj` / `sv_01m2r0vejmq3y1hy5v94dry2p0`.
> Next action: Attach this block to TAR-239 and roll the judgment into TAR-160.
