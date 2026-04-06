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
successful_runs="$(jq '[.[] | select(.conclusion=="success")] | length' "${filtered_runs_json}")"
success_run_ids="$(jq -r '.[] | select(.conclusion=="success") | .databaseId' "${filtered_runs_json}")"

screenshot_retry_events=0
artifact_downloaded_runs=0
runs_with_operator_events=0
preflight_blocked_events=0
preflight_ready_events=0
remediation_action_clicks=0
verification_opened_events=0
pipeline_health_loaded_events=0
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
    artifact_downloaded_runs=$((artifact_downloaded_runs + 1))
    events_path="${artifact_dir}/legal-search/frontend/screenshot-pack/operator-journey-events.json"
    if [[ -f "${events_path}" ]]; then
      runs_with_operator_events=$((runs_with_operator_events + 1))
      metrics_path="${tmp_root}/event-metrics-${run_id}.json"
      python3 - <<PY > "${metrics_path}"
import json
from collections import Counter

events = json.load(open("${events_path}", "r", encoding="utf-8"))
blocked_counter = Counter()
metrics = Counter()
for event in events:
    event_name = str(event.get("event") or "")
    if event_name:
        metrics[event_name] += 1
    if event_name == "preflight_blocked":
        for code in event.get("readiness_codes") or []:
            blocked_counter[str(code)] += 1
print(json.dumps({
    "blocked_counts": blocked_counter,
    "preflight_blocked_events": int(metrics.get("preflight_blocked", 0)),
    "preflight_ready_events": int(metrics.get("preflight_ready", 0)),
    "remediation_action_clicks": int(metrics.get("remediation_action_clicked", 0)),
    "verification_opened_events": int(metrics.get("legal_search_verification_opened", 0)),
    "pipeline_health_loaded_events": int(metrics.get("pipeline_health_loaded", 0)),
}))
PY
      preflight_blocked_events=$((preflight_blocked_events + $(jq '.preflight_blocked_events // 0' "${metrics_path}")))
      preflight_ready_events=$((preflight_ready_events + $(jq '.preflight_ready_events // 0' "${metrics_path}")))
      remediation_action_clicks=$((remediation_action_clicks + $(jq '.remediation_action_clicks // 0' "${metrics_path}")))
      verification_opened_events=$((verification_opened_events + $(jq '.verification_opened_events // 0' "${metrics_path}")))
      pipeline_health_loaded_events=$((pipeline_health_loaded_events + $(jq '.pipeline_health_loaded_events // 0' "${metrics_path}")))

      python3 - <<PY > "${tmp_root}/blocked-${run_id}.json"
import json
print(json.dumps(json.load(open("${metrics_path}", "r", encoding="utf-8")).get("blocked_counts", {})))
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

confidence_json="${tmp_root}/confidence.json"
python3 - <<PY > "${confidence_json}"
import json

total_runs = int("${total_runs}")
failed_runs = int("${failed_runs}")
successful_runs = int("${successful_runs}")
artifact_downloaded_runs = int("${artifact_downloaded_runs}")
runs_with_operator_events = int("${runs_with_operator_events}")

def pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return (numerator / denominator) * 100.0

success_rate_pct = pct(total_runs - failed_runs, total_runs)
artifact_coverage_pct = pct(artifact_downloaded_runs, successful_runs)
telemetry_coverage_pct = pct(runs_with_operator_events, successful_runs)

marker = "high"
reasons = []
if total_runs < 3:
    marker = "low"
    reasons.append("Low sample size (<3 runs)")
if success_rate_pct < 80.0:
    marker = "low"
    reasons.append("Success rate below 80%")
if marker != "low" and (artifact_coverage_pct < 80.0 or telemetry_coverage_pct < 60.0):
    marker = "medium"
    reasons.append("Artifact or telemetry coverage below target")
if not reasons:
    reasons = ["Stable sample size, pass rate, and evidence coverage"]

print(
    json.dumps(
        {
            "marker": marker,
            "reason": "; ".join(reasons),
            "success_rate_pct": success_rate_pct,
            "artifact_coverage_pct": artifact_coverage_pct,
            "telemetry_coverage_pct": telemetry_coverage_pct,
        }
    )
)
PY

confidence_marker="$(jq -r '.marker' "${confidence_json}")"
confidence_reason="$(jq -r '.reason' "${confidence_json}")"
success_rate_pct="$(jq -r '.success_rate_pct | tostring' "${confidence_json}")"
artifact_coverage_pct="$(jq -r '.artifact_coverage_pct | tostring' "${confidence_json}")"
telemetry_coverage_pct="$(jq -r '.telemetry_coverage_pct | tostring' "${confidence_json}")"

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
| Successful staging evidence runs | ${successful_runs} |
| Failed staging evidence runs | ${failed_runs} |
| Success rate | ${success_rate_pct}% |
| Screenshot-pack retries invoked | ${screenshot_retry_events} |
| Artifact downloads from successful runs | ${artifact_downloaded_runs}/${successful_runs} |
| Operator telemetry coverage | ${runs_with_operator_events}/${successful_runs} |
| Evidence confidence marker | ${confidence_marker} |

## Confidence Notes

- Marker: \`${confidence_marker}\`
- Why: ${confidence_reason}
- Artifact coverage: ${artifact_coverage_pct}%
- Telemetry coverage: ${telemetry_coverage_pct}%

## Operator Journey Signals

| Signal | Value |
| --- | ---: |
| Preflight blocked events | ${preflight_blocked_events} |
| Preflight ready events | ${preflight_ready_events} |
| Remediation action clicks | ${remediation_action_clicks} |
| Pipeline health loaded events | ${pipeline_health_loaded_events} |
| Legal-search verification opened events | ${verification_opened_events} |

## Blocked Launch Frequency By Readiness Code

| Readiness code | Count |
| --- | ---: |
${blocked_table_rows}
EOF

echo "Wrote KPI report to ${OUTPUT_PATH}"
