#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-}"
REGION="${REGION:-europe-west6}"
REPOSITORY="${REPOSITORY:-runtime}"

if [[ -z "${PROJECT_ID}" ]]; then
  echo "PROJECT_ID is required (e.g. project-dacd6b7b-dc96-4534-b82)." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
# Full commit SHA matches platform-control-cd.yml / runtime-images primary tags.
DEFAULT_TAG="${GITHUB_SHA:-$(git -C "${ROOT_DIR}" rev-parse HEAD 2>/dev/null || echo latest)}"
TAG="${TAG:-${DEFAULT_TAG}}"

build_image() {
  local context="$1"
  local dockerfile="$2"
  local image_name="$3"
  local image_uri="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${image_name}:${TAG}"

  echo "Building ${image_uri}"
  gcloud builds submit "${ROOT_DIR}" \
    --project="${PROJECT_ID}" \
    --config="${ROOT_DIR}/scripts/cloudbuild.runtime-image.yaml" \
    --substitutions="_IMAGE=${image_uri},_DOCKERFILE=${dockerfile},_CONTEXT=${context}"
}

# Run independent image builds concurrently (separate Cloud Build jobs). Watch project
# concurrent build quotas if you add many more images here.
pids=()
build_image "." "platform-control/Dockerfile" "platform-control" &
pids+=($!)
build_image "platform-control" "platform-control/Dockerfile.worker" "platform-control-worker" &
pids+=($!)
build_image "." "legal-search/api/Dockerfile" "legal-search-api" &
pids+=($!)
build_image "." "document-intelligence/Dockerfile" "di-consumer" &
pids+=($!)

exit_status=0
for pid in "${pids[@]}"; do
  if ! wait "${pid}"; then
    exit_status=1
  fi
done

if [[ "${exit_status}" -ne 0 ]]; then
  echo "One or more image builds failed." >&2
  exit "${exit_status}"
fi

echo "Done. Built runtime images with tag: ${TAG}"
