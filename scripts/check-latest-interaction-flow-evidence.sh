#!/usr/bin/env bash
set -euo pipefail

MODE="staging"
BRANCH="main"
OUTPUT_DIR="tmp/interaction-flow-evidence-quickcheck"
GITHUB_OUTPUT_PATH=""

usage() {
  cat <<'EOF'
Usage: scripts/check-latest-interaction-flow-evidence.sh [options]

Fetch the latest interaction-flow evidence artifact and verify expected files exist.

Options:
  --mode <staging|local>  Evidence source (default: staging)
  --branch <name>         Branch to inspect (default: main)
  --output-dir <path>     Output directory (default: tmp/interaction-flow-evidence-quickcheck)
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

scripts/fetch-interaction-flow-evidence.sh \
  --workflow "${WORKFLOW}" \
  --artifact-prefix "${ARTIFACT_PREFIX}" \
  --branch "${BRANCH}" \
  --output-dir "${OUTPUT_DIR}"

latest_dir="$(ls -1d "${OUTPUT_DIR}"/* 2>/dev/null | sort | tail -n 1 || true)"
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

echo "Evidence quick-check passed."
echo "Mode: ${MODE}"
echo "Run dir: ${latest_dir}"
echo "Manifest: ${manifest_path}"
echo "Playwright report: ${report_dir}"
echo "Screenshot pack: ${screenshot_pack_dir}"
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
