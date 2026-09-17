#!/usr/bin/env bash
# Replay dead-lettered events from the NATS JetStream DLQ subjects back onto the
# subjects they were meant for.
#
# WHY THIS EXISTS. `scripts/replay-dlq.sh` is a GCP Pub/Sub script — `gcloud`,
# `--project`, subscription names — and ADR-0029 retired that runtime. On
# Hetzner/NATS the DLQ had no reader at all, so a dead-lettered event was a
# permanent silent loss with the payload sitting right there in the stream.
#
# Measured 2026-09-17: 88 events (48 `document.processed`, 40
# `document.processing_status.updated`) were dead-lettered when the projection
# bridge could not authenticate. 59 documents from one acquisition run therefore
# had no `canonical_ready` in platform-control's read model, and 48 were never
# projected into OpenSearch. Nothing was lost — nothing could read it back.
#
# ON IDEMPOTENCY. Both event types are keyed by `document_id`, which is stable
# per version (#850), and both consumers upsert. Replaying an event that already
# landed is therefore a no-op rather than a duplicate. That is what makes this
# safe to re-run, and it is the property to check first if a third event type is
# ever added to the DLQ set.

set -euo pipefail

NS="${NS:-evidara}"
NATS_BOX="${NATS_BOX:-deploy/nats-box}"
NATS_URL="${NATS_URL:-nats://nats:4222}"
STREAM="${STREAM:-EVIDARA}"
DRY_RUN=0
FROM=""
TO=""
SUBJECTS=()

usage() {
  cat <<'USAGE'
Usage: scripts/replay-nats-dlq.sh [options]

  --dry-run           Enumerate and report; publish nothing.
  --subject <subj>    A `.dlq` subject to replay. Repeatable. Default: every
                      `.dlq` subject the stream currently reports.
  --from <seq>        First stream sequence to scan.
  --to <seq>          Last stream sequence to scan.
                      Default: the last 5000 sequences, which is the window a
                      recent incident lives in. Widen for an older one.

Env: NS (evidara), NATS_BOX (deploy/nats-box), NATS_URL, STREAM (EVIDARA)

The DLQ is not drained. Replayed messages stay in the stream and age out with
the retention policy, so a second run republishes them — harmless, because both
event types upsert on a stable document_id, and it keeps this script from being
the only record that a replay happened.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --subject) SUBJECTS+=("${2:?missing value for --subject}"); shift 2 ;;
    --from) FROM="${2:?missing value for --from}"; shift 2 ;;
    --to) TO="${2:?missing value for --to}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

command -v kubectl >/dev/null || { echo "error: kubectl not found" >&2; exit 1; }

in_box() { kubectl -n "$NS" exec "$NATS_BOX" -- sh -c "$1"; }

echo "==> Stream ${STREAM} on ${NATS_URL} (namespace ${NS})"
info="$(in_box "nats --server ${NATS_URL} stream info ${STREAM} --json 2>/dev/null")"
first_seq="$(printf '%s' "$info" | sed -n 's/.*"first_seq": *\([0-9]*\).*/\1/p' | head -1)"
last_seq="$(printf '%s' "$info" | sed -n 's/.*"last_seq": *\([0-9]*\).*/\1/p' | head -1)"
[[ -n "$last_seq" ]] || { echo "error: could not read stream state" >&2; exit 1; }
echo "    sequences ${first_seq}..${last_seq}"

if [[ -z "$FROM" ]]; then
  FROM=$(( last_seq > 5000 ? last_seq - 5000 : first_seq ))
fi
[[ -z "$TO" ]] && TO="$last_seq"
echo "    scanning ${FROM}..${TO}"

echo "==> DLQ subjects the stream reports"
in_box "nats --server ${NATS_URL} stream subjects ${STREAM} 2>/dev/null" \
  | grep -oE 'evidara\.[a-z-]+\.dlq[^0-9]*[0-9,]+' | sed 's/^/    /' || true

subject_filter=""
if [[ ${#SUBJECTS[@]} -gt 0 ]]; then
  # A literal, anchored match per subject — never a substring, or
  # `document-processed.dlq` would also select `document-processed-foo.dlq`.
  for s in "${SUBJECTS[@]}"; do subject_filter="${subject_filter}${subject_filter:+|}^${s}\$"; done
  echo "    restricted to: ${SUBJECTS[*]}"
fi

# Read-only enumeration. A per-sequence `stream get` is slow but needs no
# consumer, so it cannot disturb delivery state for a live subscriber — which
# matters when the thing being repaired is a delivery failure.
echo "==> Enumerating (read-only)"
found="$(in_box "
for seq in \$(seq ${FROM} ${TO}); do
  s=\$(nats --server ${NATS_URL} stream get ${STREAM} \"\$seq\" --json 2>/dev/null | sed -n 's/.*\"subject\": \"\(.*\)\".*/\1/p' | head -1)
  case \"\$s\" in *.dlq) echo \"\$seq \$s\";; esac
done")"

if [[ -n "$subject_filter" ]]; then
  found="$(printf '%s\n' "$found" | awk '{print $2}' | grep -nE "$subject_filter" >/dev/null 2>&1 && printf '%s\n' "$found" | awk -v f="$subject_filter" '$2 ~ f' || true)"
fi

count="$(printf '%s\n' "$found" | grep -c . || true)"
echo "    ${count} dead-lettered message(s)"
[[ "$count" -eq 0 ]] && { echo "==> Nothing to replay."; exit 0; }
printf '%s\n' "$found" | awk '{print $2}' | sort | uniq -c | sed 's/^/    /'

if [[ "$DRY_RUN" == 1 ]]; then
  echo "==> DRY RUN — nothing published."
  echo "    Re-run without --dry-run to replay these ${count} message(s)."
  exit 0
fi

seqs="$(printf '%s\n' "$found" | awk '{print $1}' | tr '\n' ' ')"
echo "==> Republishing"
# Each message is re-read inside the box rather than shipped out and back, so the
# payload never round-trips through this shell's quoting.
result="$(in_box "
ok=0; fail=0
for seq in ${seqs}; do
  j=\$(nats --server ${NATS_URL} stream get ${STREAM} \"\$seq\" --json 2>/dev/null)
  sub=\$(echo \"\$j\" | sed -n 's/.*\"subject\": \"\(.*\)\".*/\1/p' | head -1)
  case \"\$sub\" in *.dlq) ;; *) echo \"  seq \$seq: subject \$sub is not a DLQ — skipped\"; continue;; esac
  target=\$(echo \"\$sub\" | sed 's/\.dlq\$//')
  body=\$(echo \"\$j\" | sed -n 's/.*\"data\": \"\(.*\)\".*/\1/p' | head -1 | base64 -d)
  if [ -z \"\$body\" ]; then echo \"  seq \$seq: empty payload — skipped\"; fail=\$((fail+1)); continue; fi
  # --no-templates: the payload is JSON and must not be interpreted as a Go template.
  if printf '%s' \"\$body\" | nats --server ${NATS_URL} pub \"\$target\" --force-stdin --no-templates >/dev/null 2>&1; then
    ok=\$((ok+1))
  else
    echo \"  seq \$seq: publish to \$target FAILED\"; fail=\$((fail+1))
  fi
done
echo \"REPLAY ok=\$ok fail=\$fail\"
")"
printf '%s\n' "$result" | sed 's/^/    /'

summary="$(printf '%s\n' "$result" | grep '^REPLAY' | tail -1)"
ok="$(printf '%s' "$summary" | sed -n 's/.*ok=\([0-9]*\).*/\1/p')"
fail="$(printf '%s' "$summary" | sed -n 's/.*fail=\([0-9]*\).*/\1/p')"

echo "==> Replayed ${ok:-0} of ${count}; ${fail:-0} failed."
if [[ "${fail:-0}" -ne 0 || "${ok:-0}" -ne "$count" ]]; then
  echo "error: not every message was republished. Re-run to retry — the events" >&2
  echo "       upsert on a stable document_id, so a replayed one is a no-op." >&2
  exit 1
fi
echo "    Consumers pick these up asynchronously. Verify with the run's"
echo "    processing-status and the legal-search coverage count, not with this exit code."
