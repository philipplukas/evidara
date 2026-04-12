# TAR-64 / TAR-85 — evidence capture (operator)

Owner: Platform  
Last reviewed: 2026-04-11  
Last verified: 2026-04-11  
Applies to: Linear **TAR-64** (dev e2e smoke ×2), **TAR-85** (remote MVP acceptance — **dev** when no staging GCP project)

Use this when attaching **run output** to Linear so reviewers can find commands and expected artifacts without rereading the full M5 memo.

## TAR-64 — two dev smoke runs

1. Follow [M5 evidence checklist](m5-evidence-checklist.md) (section **TAR-64**).
2. Run **twice** on separate calendar times (or two distinct GitHub Actions `workflow_dispatch` runs).
3. For **each** run, attach to **TAR-64**:
   - Timestamp (UTC) and **run URL** (GitHub Actions) **or** terminal transcript path
   - Final exit code (`0` expected)
   - If step 7 (DI signals) failed: paste the script’s diagnostic block and follow the “Debugging e2e step 7” list in the checklist

**Command (local):**

```bash
EVIDARA_GCP_IMPERSONATE_SERVICE_ACCOUNT='…' GCP_PROJECT_ID='…' \
  ./scripts/e2e-smoke-test.sh --env dev
```

## TAR-85 — remote MVP acceptance (dev-first)

1. Follow [M5 evidence checklist](m5-evidence-checklist.md) (section **TAR-85**).
2. Point CLI at **dev** base URLs (or **staging** if you operate it) and mint tokens per checklist.
3. Attach to **TAR-85**:
   - Redacted `evidara workflow mvp-acceptance` stdout **or** `--json` output file
   - Note which scenarios passed/failed vs [MVP acceptance scenario pack](mvp-acceptance-scenario-pack.md)

**Command:**

```bash
./scripts/evidara-cloud-run-operator-session.sh dev --mvp-only
# or manually:
cd tools/evidara-cli && uv run evidara workflow mvp-acceptance --human
# or: ... mvp-acceptance --json > /tmp/mvp-acceptance-dev.json
```

## Committed snapshots (2026-04-09)

See [`evidence/README.md`](evidence/README.md): staging MVP acceptance JSON (two runs), staging relevance markdown, dev e2e **blocker** note when Cloud Run API/project access is missing, and [**GitHub E2E dispatch attempts**](evidence/2026-04-09-e2e-github-dispatch-tar64.md) for TAR-64.

## Definition of done (for closing the Linear issues)

- **TAR-64:** two successful runs + evidence linked in issue comments or attachments.
- **TAR-85:** at least one green **remote** run (typically **dev** Cloud Run) with captured output linked on the issue.
