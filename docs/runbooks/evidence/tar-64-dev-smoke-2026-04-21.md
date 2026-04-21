# TAR-64 Dev Smoke Evidence (2026-04-21)

## Summary

Two successful E2E Smoke Dev runs on current `main` (`7220e88`), both on
GitHub-hosted runners after migrating workflows from degraded self-hosted pool.

## Runs

| Run | Conclusion | Started (UTC) | Finished (UTC) | URL |
|-----|------------|---------------|----------------|-----|
| 1 | **success** | 2026-04-21 11:36:01 | 2026-04-21 11:57:00 | [24720182399](https://github.com/philipplukas/evidara/actions/runs/24720182399) |
| 2 | **success** | 2026-04-21 11:36:36 | 2026-04-21 11:56:57 | [24720205793](https://github.com/philipplukas/evidara/actions/runs/24720205793) |

## Pipeline steps verified

Both runs executed the full 9-step E2E pipeline:

1. Health checks (platform-control + legal-search)
2. Seed reference data (jurisdictions, authorities)
3. Create source
4. Create and approve source version
5. Trigger acquisition run
6. Poll for run completion
7. Verify DI signals (canonical_ready + document.processed)
8. Check projection history
9. Search for indexed document

## Context

- Workflows were blocked on degraded `evidara-heavy-v2` self-hosted runners
- PRs #327 and #328 migrated all CI workflows to `ubuntu-latest`
- Worker image was rebuilt from current main via Cloud Build (stale image was crash-looping)
- Worker `minScale` set to 1 to keep polling instance warm

## Exit criteria

TAR-64 requires two green dev smoke passes on current `main`. Both runs
completed successfully — exit criteria met.
