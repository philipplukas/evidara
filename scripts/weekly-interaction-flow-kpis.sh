#!/usr/bin/env bash
set -euo pipefail

DAYS=7
WORKFLOW="Interaction Flow Staging Evidence"
BRANCH="main"
LIMIT=50
OUTPUT_PATH="tmp/interaction-flow-kpis.md"

usage() {
  cat <<'EOF'
Usage: scripts/weekly-interaction-flow-kpis.sh [options]

Compute weekly interaction-flow KPIs from GitHub Actions runs/artifacts.

Options:
  --days <n>          Number of days to look back (default: 7)
  --workflow <name>   Workflow name to analyze (default: "Interaction Flow Staging Evidence")
  --branch <name>     Branch to inspect (default: "main")
  --limit <n>         Max runs to inspect before date filtering (default: 50)
  --output <path>     Markdown output path (default: tmp/interaction-flow-kpis.md)
  -h, --help          Show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --days)
      DAYS="${2:?missing value for --days}"
      shift 2
      ;;
    --workflow)
      WORKFLOW="${2:?missing value for --workflow}"
      shift 2
      ;;
    --branch)
      BRANCH="${2:?missing value for --branch}"
      shift 2
      ;;
    --limit)
      LIMIT="${2:?missing value for --limit}"
      shift 2
      ;;
    --output)
      OUTPUT_PATH="${2:?missing value for --output}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI is required." >&2
  exit 1
fi
if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required." >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required." >&2
  exit 1
fi

mkdir -p "$(dirname "${OUTPUT_PATH}")"
tmp_root="$(mktemp -d)"
trap 'rm -rf "${tmp_root}"' EXIT

runs_json="${tmp_root}/runs.json"
gh run list \
  --workflow "${WORKFLOW}" \
  --branch "${BRANCH}" \
  --limit "${LIMIT}" \
  --json databaseId,createdAt,conclusion,url \
  > "${runs_json}"

cutoff_iso="$(python3 - <<PY
from datetime import datetime, timedelta, timezone
days = int("${DAYS}")
print((datetime.now(timezone.utc) - timedelta(days=days)).isoformat().replace("+00:00","Z"))
PY
)"

filtered_runs_json="${tmp_root}/filtered-runs.json"
python3 - <<PY > "${filtered_runs_json}"
import json
from datetime import datetime, timezone

cutoff = datetime.fromisoformat("${cutoff_iso}".replace("Z","+00:00"))
runs = json.load(open("${runs_json}", "r", encoding="utf-8"))
filtered = []
for run in runs:
    created_at = run.get("createdAt")
    if not created_at:
        continue
    dt = datetime.fromisoformat(created_at.replace("Z","+00:00"))
    if dt >= cutoff:
        filtered.append(run)
print(json.dumps(filtered))
PY

total_runs="$(jq 'length' "${filtered_runs_json}")"
failed_runs="$(jq '[.[] | select((.conclusion // "unknown") != "success")] | length' "${filtered_runs_json}")"
success_run_ids="$(jq -r '.[] | select(.conclusion=="success") | .databaseId' "${filtered_runs_json}")"

screenshot_retry_events=0
blocked_counts_json="${tmp_root}/blocked-counts.json"
echo '{}' > "${blocked_counts_json}"

while IFS= read -r run_id; do
  [[ -z "${run_id}" ]] && continue

  run_log="${tmp_root}/run-${run_id}.log"
  if gh run view "${run_id}" --log > "${run_log}" 2>/dev/null; then
    count="$(python3 - <<PY
import re
text = open("${run_log}", "r", encoding="utf-8", errors="ignore").read()
print(len(re.findall(r"Screenshot pack failed on attempt", text)))
PY
)"
    screenshot_retry_events=$((screenshot_retry_events + count))
  fi

  artifact_dir="${tmp_root}/artifact-${run_id}"
  mkdir -p "${artifact_dir}"
  if gh run download "${run_id}" --name "interaction-flow-staging-evidence-${run_id}" --dir "${artifact_dir}" >/dev/null 2>&1; then
    events_path="${artifact_dir}/legal-search/frontend/screenshot-pack/operator-journey-events.json"
    if [[ -f "${events_path}" ]]; then
      python3 - <<PY > "${tmp_root}/blocked-${run_id}.json"
import json
from collections import Counter

events = json.load(open("${events_path}", "r", encoding="utf-8"))
counter = Counter()
for event in events:
    if event.get("event") != "preflight_blocked":
        continue
    for code in event.get("readiness_codes") or []:
        counter[str(code)] += 1
print(json.dumps(counter))
PY
      python3 - <<PY > "${tmp_root}/blocked-merged-${run_id}.json"
import json
from collections import Counter

base = Counter(json.load(open("${blocked_counts_json}", "r", encoding="utf-8")))
inc = Counter(json.load(open("${tmp_root}/blocked-${run_id}.json", "r", encoding="utf-8")))
base.update(inc)
print(json.dumps(base))
PY
      mv "${tmp_root}/blocked-merged-${run_id}.json" "${blocked_counts_json}"
    fi
  fi
done <<< "${success_run_ids}"

blocked_table_rows="$(python3 - <<PY
import json
counts = json.load(open("${blocked_counts_json}", "r", encoding="utf-8"))
if not counts:
    print("| n/a | 0 |")
else:
    for code, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"| {code} | {count} |")
PY
)"

generated_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cat <<EOF > "${OUTPUT_PATH}"
# Weekly Interaction-Flow KPIs

- Generated at: \`${generated_at}\`
- Window: last \`${DAYS}\` day(s)
- Workflow: \`${WORKFLOW}\`
- Branch: \`${BRANCH}\`

## Summary

| KPI | Value |
| --- | ---: |
| Staging evidence runs inspected | ${total_runs} |
| Failed staging evidence runs | ${failed_runs} |
| Screenshot-pack retries invoked | ${screenshot_retry_events} |

## Blocked Launch Frequency By Readiness Code

| Readiness code | Count |
| --- | ---: |
${blocked_table_rows}
EOF

echo "Wrote KPI report to ${OUTPUT_PATH}"
