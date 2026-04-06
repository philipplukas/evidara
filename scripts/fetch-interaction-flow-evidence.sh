#!/usr/bin/env bash
set -euo pipefail

WORKFLOW="Legal Search"
ARTIFACT_PREFIX="interaction-flow-evidence"
BRANCH="main"
OUTPUT_DIR="tmp/interaction-flow-evidence"
RUN_ID=""

usage() {
  cat <<'EOF'
Usage: scripts/fetch-interaction-flow-evidence.sh [options]

Download the latest available interaction-flow evidence artifact from GitHub Actions.

Options:
  --workflow <name>          Workflow name (default: "Legal Search")
  --artifact-prefix <prefix> Artifact prefix (default: "interaction-flow-evidence")
  --branch <name>            Branch to scan (default: "main")
  --run-id <id>              Explicit run ID to download from
  --output-dir <path>        Output directory (default: "tmp/interaction-flow-evidence")
  -h, --help                 Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --workflow)
      WORKFLOW="${2:?missing value for --workflow}"
      shift 2
      ;;
    --artifact-prefix)
      ARTIFACT_PREFIX="${2:?missing value for --artifact-prefix}"
      shift 2
      ;;
    --branch)
      BRANCH="${2:?missing value for --branch}"
      shift 2
      ;;
    --run-id)
      RUN_ID="${2:?missing value for --run-id}"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="${2:?missing value for --output-dir}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI is required but not installed." >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required but not installed." >&2
  exit 1
fi

mkdir -p "${OUTPUT_DIR}"

download_artifact_for_run() {
  local run_id="$1"
  local run_url="$2"
  local artifact_name="${ARTIFACT_PREFIX}-${run_id}"
  local target_dir="${OUTPUT_DIR}/${run_id}"
  mkdir -p "${target_dir}"

  if gh run download "${run_id}" --name "${artifact_name}" --dir "${target_dir}" >/dev/null 2>&1; then
    echo "Downloaded ${artifact_name} from run ${run_id}"
    echo "Run URL: ${run_url}"
    echo "Output: ${target_dir}"
    return 0
  fi

  rmdir "${target_dir}" 2>/dev/null || true
  return 1
}

if [[ -n "${RUN_ID}" ]]; then
  run_json="$(gh run view "${RUN_ID}" --json databaseId,url)"
  run_url="$(echo "${run_json}" | jq -r '.url')"
  if download_artifact_for_run "${RUN_ID}" "${run_url}"; then
    exit 0
  fi
  echo "Artifact ${ARTIFACT_PREFIX}-${RUN_ID} not found." >&2
  exit 2
fi

runs_json="$(gh run list \
  --workflow "${WORKFLOW}" \
  --branch "${BRANCH}" \
  --limit 30 \
  --json databaseId,conclusion,url)"

mapfile -t run_rows < <(echo "${runs_json}" | jq -r '.[] | select(.conclusion=="success") | "\(.databaseId) \(.url)"')

if [[ ${#run_rows[@]} -eq 0 ]]; then
  echo "No successful runs found for workflow '${WORKFLOW}' on branch '${BRANCH}'." >&2
  exit 2
fi

for row in "${run_rows[@]}"; do
  run_id="${row%% *}"
  run_url="${row#* }"
  if download_artifact_for_run "${run_id}" "${run_url}"; then
    exit 0
  fi
done

echo "No artifact with prefix '${ARTIFACT_PREFIX}' found in recent successful runs." >&2
exit 2
