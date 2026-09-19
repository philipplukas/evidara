#!/usr/bin/env bash
# Backfill a terminal processing status for documents that entered processing and
# never came out — the operator half of #1038.
#
# WHY A BACKFILL AT ALL. The CronJob
# (`infra/hetzner/apps/processing-reclaim-cronjob.yaml`) reclaims everything from
# the moment it is deployed, including the documents already stranded. This script
# exists so an operator can do it deliberately, now, with a dry run first and a
# per-run scope, instead of waiting for the next cron tick and reading about it
# afterwards.
#
# WHAT WAS STRANDED WHEN THIS SHIPPED. Measured 2026-09-19 against production: 116
# documents with no terminal status, 58 in `run_01m26a84j0gdmeh9g5f8b1k36k`
# (2026-09-10) and 58 in `run_01m2q5fsqmarc3mxvfpsw1jjdt` (2026-09-17). Both runs
# report `status=completed`. `1901 known - 116 = 1785`, which is the search index's
# document count exactly.
#
# WHAT IT DOES NOT DO. It does not reprocess anything. It writes the terminal row
# that says the control plane stopped waiting, so the documents stop being
# invisible; getting them into the corpus is a replay, and that is a separate
# decision with a separate command (`scripts/replay-nats-dlq.sh`, or a fresh run).
#
# Runbook: docs/runbooks/processing-reclaim.md.

set -euo pipefail

NS="${NS:-evidara}"
DEPLOY="${DEPLOY:-deploy/platform-control}"
DEADLINE_HOURS="${DEADLINE_HOURS:-24}"
DRY_RUN=1
RUN_ID=""

usage() {
  cat <<'USAGE'
Usage: scripts/reclaim-stuck-processing.sh [options]

  --apply             Write the terminal rows. WITHOUT THIS THE SCRIPT ONLY
                      REPORTS — the default is a dry run on purpose.
  --run-id <run>      Reclaim only this run's units. Repeat the command per run
                      to stage the backfill; omit to sweep every run.
  --deadline-hours N  How long a unit must have been silent (default: 24).
                      Lowering this does not make a unit broken; it only decides
                      when the control plane stops waiting.

Env: NS (evidara), DEPLOY (deploy/platform-control), DEADLINE_HOURS (24)

Reads nothing from your shell but kubectl context. The sweep runs inside the
platform-control pod, which already holds the database credentials — no secret is
materialised on the workstation.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) DRY_RUN=0; shift ;;
    --run-id) RUN_ID="${2:-}"; shift 2 ;;
    --deadline-hours) DEADLINE_HOURS="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$DEADLINE_HOURS" ]] || ! [[ "$DEADLINE_HOURS" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "--deadline-hours must be a positive number" >&2
  exit 2
fi

cmd=(platform-control-processing-reclaim --deadline-hours "$DEADLINE_HOURS")
[[ -n "$RUN_ID" ]] && cmd+=(--run-id "$RUN_ID")
if [[ "$DRY_RUN" -eq 1 ]]; then
  cmd+=(--dry-run)
  echo "DRY RUN — nothing will be written. Re-run with --apply to write." >&2
fi

echo "kubectl -n $NS exec $DEPLOY -- ${cmd[*]}" >&2
kubectl -n "$NS" exec "$DEPLOY" -- "${cmd[@]}"
