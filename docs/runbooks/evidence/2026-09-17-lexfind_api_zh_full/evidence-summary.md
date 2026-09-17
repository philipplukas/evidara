# CH LexFind Fast Loop Evidence Summary

- Environment: `dev`
- Template: `lexfind_api_zh_full`
- Source: `src_01m2q5fs0ytzrfa31drw12qqgj`
- Source version: `sv_01m2qyjtndxkx4gmhq42w71m35`
- Run: `run_01m2qyjv550m1yrnnd70zndf9f`
- Verdict: `pass`
- Max resources: `10`
- Run mode: `acceptance`
- Started at (UTC): `2026-09-17T15:08:24Z`
- Completed at (UTC): `2026-09-17T15:10:42Z`
- Run dir: `/tmp/claude-1000/-home-philipp-Projects-evidara/7bf473c8-0299-4d12-bc66-c25e7b989375/scratchpad/evidence/zh_full_5`
- Jurisdiction: `jur_ch_zh`
- Authority: `auth_zh_sk`

## Gate coverage

- `title_ok` — **excluded** (`no_expected_title_declared`): deliberately not asserted for this corpus, so it is unverified but not a hole.
- `body_lang_hint_ok` — **excluded** (`not_a_german_template`): deliberately not asserted for this corpus, so it is unverified but not a hole.
- `indexed_title_ok` — **excluded** (`no_expected_title_declared`): deliberately not asserted for this corpus, so it is unverified but not a hole.

## Checks

- `captured_count=8`
- `raw_artifact_count=8`
- `expect_content_type=application/pdf`
- `content_type_match_count=8`
- `url_pattern=lexfind\.ch/`
- `accepted_count=8`
- `processing_count=8`
- `canonical_ready_count=8`
- `processed_count=7`
- `title_ok=8`
- `title_checked=0`
- `indexed_title_ok=1`
- `indexed_title_checked=0`
- `indexed_title_observed=doc_00ad45yebp9mcers848nnhm6yh=Vollzugsverordnung zum Personalgesetz (VVO) 177.111,doc_1yzc1hxnzjymcr5q000a21xbbs=Kantonsverfassung 101,doc_3zh0f1kbe2nzxswx76d8t22sk4=Einführungsgesetz zum Krankenversicherungsgesetz (EG KVG) 832.01,doc_4qsyxtemnb29cckqq507wvj0dc=112,doc_5tzexsdt1rskb0fv8vjkgr74m4=Verordnung über die Datenbearbeitung der JI 172.110.11,doc_65cwcchj01yswqbmczcavytp8f=Organisationsverordnung – Direktion der Justiz und des Innern 172.110.1,doc_6why4h2gtfgqqmzfjeqv9jc631=Gesetz über die politischen Rechte (GPR) 161`
- `url_pattern_ok=8`
- `art1_ok=3`
- `art_density_count=190`
- `art_density_ok=1`
- `content_gate_source=canonical`
- `body_max_length=152853`
- `min_content_length_ok=1`
- `lang_agreement_ok=1`
- `body_lang_hint_ok=1`
- `body_lang_hint_checked=0`
- `skipped_gates=["title_ok","body_lang_hint_ok","indexed_title_ok"]`
- `gate_coverage=[{"gate":"title_ok","outcome":"excluded","reason":"no_expected_title_declared"},{"gate":"body_lang_hint_ok","outcome":"excluded","reason":"not_a_german_template"},{"gate":"indexed_title_ok","outcome":"excluded","reason":"no_expected_title_declared"}]`
- `excluded_gates=["title_ok","body_lang_hint_ok","indexed_title_ok"]`
- `not_evaluated_gates=[]`
- `indexed_language_expected=de`
- `indexed_language_observed=doc_00ad45yebp9mcers848nnhm6yh=de,doc_1yzc1hxnzjymcr5q000a21xbbs=de,doc_3zh0f1kbe2nzxswx76d8t22sk4=de,doc_4qsyxtemnb29cckqq507wvj0dc=de,doc_5tzexsdt1rskb0fv8vjkgr74m4=de,doc_65cwcchj01yswqbmczcavytp8f=de,doc_6why4h2gtfgqqmzfjeqv9jc631=de`
- `indexed_language_checked=1`
- `indexed_language_ok=1`
- `as_of_utc=2026-09-17`
- `in_force_from_present=8`
- `future_dated_count=0`
- `not_in_force_count=0`
- `in_force_ok=1`

## TAR-239 / TAR-160 Paste Block

> CH LexFind fast loop `lexfind_api_zh_full` on `dev` returned `pass` (`run_01m2qyjv550m1yrnnd70zndf9f`).
> Checks: captured=`8`, raw_artifacts=`8`, application/pdf=`8`, DI accepted/processing/canonical_ready=`8/8/8`, lifecycle processed=`7`.
> Run mode: `acceptance` — an acceptance rehearsal, not production ingest; it does not imply either ADR-0030 key is turned.
> Gates excluded (not applicable, not asserted): `title_ok`, `body_lang_hint_ok`, `indexed_title_ok`.
> Gates NOT EVALUATED (asked for, could not run): none.
> Source/version: `src_01m2q5fs0ytzrfa31drw12qqgj` / `sv_01m2qyjtndxkx4gmhq42w71m35`.
> Next action: Attach this block to TAR-239 and roll the judgment into TAR-160.
