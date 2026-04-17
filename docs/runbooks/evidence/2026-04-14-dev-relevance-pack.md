# 2026-04-14 Dev Relevance Pack

Owner: Platform / GA
Environment: `dev`
Verified at (UTC): `2026-04-14`
Status: completed with `pass` judgment

## Summary

This note refreshes the dev relevance evidence after the replay / projection fixes.
The corpus is no longer empty: `q=*` returns results again. The CH proof doc now
resolves with the corrected title. The AT proof doc still renders as `RIS Dokument`,
so that title cleanup remains a projection follow-up. Broader ranking on short legal
queries remains open.

## Observations

- Control row `q=*`: non-empty, `totalResults=103`
- CH proof doc `doc_1wxstrwdxtwh0zaxag6x37hya2`: `Bundesverfassung der Schweizerischen Eidgenossenschaft vom 18. April 1999`, `document_type=law`
- AT proof doc `doc_7m5fzs4ksj057ft0sgzqaecpyh`: `law`, title still `RIS Dokument`
- Seed queries `Bundesgericht`, `Art. 8 EMRK`, `BVGE`: still generic top hits / `unknown`

## Interpretation

`q=*` no longer indicates empty-index or alias drift. The remaining issue is ranking
discrimination on broad legal queries, with a separate residual projection/title cleanup
on AT.

## Judgment

- Corpus-health: `pass`
- CH proof-doc recovery: `pass`
- AT title cleanup: `partial`
- Broader relevance ranking: `open`
- Follow-up lanes: `TAR-241` (ranking) and `TAR-242` (projection/title cleanup)
