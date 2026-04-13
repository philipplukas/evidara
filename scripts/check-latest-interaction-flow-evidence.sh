#!/usr/bin/env bash
set -euo pipefail

MODE="staging"
BRANCH="main"
OUTPUT_DIR="tmp/interaction-flow-evidence-quickcheck"
GITHUB_OUTPUT_PATH=""
GCS_ROOT_URI=""

usage() {
  cat <<'EOF'
Usage: scripts/check-latest-interaction-flow-evidence.sh [options]

Fetch the latest interaction-flow evidence artifact and verify expected files exist.

Options:
  --mode <staging|local>  Evidence source (default: staging)
  --branch <name>         Branch to inspect (default: main)
  --output-dir <path>     Output directory (default: tmp/interaction-flow-evidence-quickcheck)
  --gcs-root-uri <uri>    Optional GCS root URI for staging evidence bundles
  --github-output <path>  Optional GitHub Actions output file path
  -h, --help              Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="${2:?missing value for --mode}"
      shift 2
      ;;
    --branch)
      BRANCH="${2:?missing value for --branch}"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="${2:?missing value for --output-dir}"
      shift 2
      ;;
    --gcs-root-uri)
      GCS_ROOT_URI="${2:?missing value for --gcs-root-uri}"
      shift 2
      ;;
    --github-output)
      GITHUB_OUTPUT_PATH="${2:?missing value for --github-output}"
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

if [[ "${MODE}" != "staging" && "${MODE}" != "local" ]]; then
  echo "--mode must be one of: staging, local" >&2
  exit 1
fi

WORKFLOW="Legal Search"
ARTIFACT_PREFIX="interaction-flow-evidence"
if [[ "${MODE}" == "staging" ]]; then
  WORKFLOW="Interaction Flow Staging Evidence"
  ARTIFACT_PREFIX="interaction-flow-staging-evidence"
fi

if [[ "${MODE}" == "staging" && -n "${GCS_ROOT_URI}" ]]; then
  if ! command -v gcloud >/dev/null 2>&1; then
    echo "gcloud CLI is required when --gcs-root-uri is provided." >&2
    exit 1
  fi
  latest_run_id="$(gh run list \
    --workflow "${WORKFLOW}" \
    --branch "${BRANCH}" \
    --limit 20 \
    --json databaseId,conclusion \
    --jq '.[] | select(.conclusion=="success") | .databaseId' | sed -n '1p')"
  if [[ -z "${latest_run_id}" ]]; then
    echo "No successful ${WORKFLOW} runs found on branch ${BRANCH}." >&2
    exit 2
  fi
  latest_dir="${OUTPUT_DIR}/${latest_run_id}"
  mkdir -p "${latest_dir}"
  gcloud storage cp --recursive \
    "${GCS_ROOT_URI%/}/interaction-flow-evidence/staging/${latest_run_id}/*" \
    "${latest_dir}/"
  echo "Downloaded staging evidence bundle from GCS for run ${latest_run_id}"
else
  scripts/fetch-interaction-flow-evidence.sh \
    --workflow "${WORKFLOW}" \
    --artifact-prefix "${ARTIFACT_PREFIX}" \
    --branch "${BRANCH}" \
    --output-dir "${OUTPUT_DIR}"
fi

latest_dir="$(ls -1d "${OUTPUT_DIR}"/* 2>/dev/null | sort -n | tail -n 1 || true)"
if [[ -z "${latest_dir}" ]]; then
  echo "No downloaded run directory found under ${OUTPUT_DIR}" >&2
  exit 2
fi

manifest_path="${latest_dir}/legal-search/frontend/${ARTIFACT_PREFIX}.md"
if [[ "${MODE}" == "staging" ]]; then
  manifest_path="${latest_dir}/legal-search/frontend/interaction-flow-staging-evidence.md"
fi

report_dir="${latest_dir}/legal-search/frontend/playwright-report"
screenshot_pack_dir="${latest_dir}/legal-search/frontend/screenshot-pack"
runbook_path="${latest_dir}/docs/runbooks/interaction-flow-validation.md"
video_mode="$(awk -F': ' '/video_mode:/{print $2; exit}' "${manifest_path}" 2>/dev/null || true)"
video_mode="${video_mode//$'\r'/}"
video_mode="${video_mode//\`/}"
video_mode="${video_mode//\"/}"
video_mode="${video_mode#${video_mode%%[![:space:]]*}}"
video_mode="${video_mode%${video_mode##*[![:space:]]}}"

if [[ ! -f "${manifest_path}" ]]; then
  echo "Missing manifest: ${manifest_path}" >&2
  exit 2
fi
if [[ ! -d "${report_dir}" ]]; then
  echo "Missing playwright report directory: ${report_dir}" >&2
  exit 2
fi
if [[ ! -d "${screenshot_pack_dir}" ]]; then
  echo "Missing screenshot evidence pack directory: ${screenshot_pack_dir}" >&2
  exit 2
fi
if [[ ! -f "${runbook_path}" ]]; then
  echo "Missing runbook snapshot: ${runbook_path}" >&2
  exit 2
fi
if [[ "${video_mode}" == "enabled" && ! -f "${latest_dir}/legal-search/frontend/screenshot-pack/cross-surface-journey.webm" ]]; then
  echo "Missing canonical journey video while manifest declares video_mode=enabled" >&2
  exit 2
fi

echo "Evidence quick-check passed."
echo "Mode: ${MODE}"
echo "Run dir: ${latest_dir}"
echo "Manifest: ${manifest_path}"
echo "Playwright report: ${report_dir}"
echo "Screenshot pack: ${screenshot_pack_dir}"
echo "Video mode: ${video_mode:-unknown}"
echo "Runbook snapshot: ${runbook_path}"

run_id="$(basename "${latest_dir}")"
run_url=""
if [[ "${run_id}" =~ ^[0-9]+$ ]] && command -v gh >/dev/null 2>&1; then
  run_url="$(gh run view "${run_id}" --json url --jq '.url' 2>/dev/null || true)"
fi

if [[ -n "${GITHUB_OUTPUT_PATH}" ]]; then
  {
    echo "evidence_mode=${MODE}"
    echo "evidence_branch=${BRANCH}"
    echo "evidence_run_id=${run_id}"
    echo "evidence_run_url=${run_url}"
    echo "evidence_run_dir=${latest_dir}"
    echo "evidence_manifest_path=${manifest_path}"
    echo "evidence_playwright_report_dir=${report_dir}"
    echo "evidence_screenshot_pack_dir=${screenshot_pack_dir}"
    echo "evidence_runbook_snapshot_path=${runbook_path}"
  } >> "${GITHUB_OUTPUT_PATH}"
fi
