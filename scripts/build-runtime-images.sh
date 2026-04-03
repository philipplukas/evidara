#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-}"
REGION="${REGION:-europe-west6}"
REPOSITORY="${REPOSITORY:-runtime}"
TAG="${TAG:-latest}"

if [[ -z "${PROJECT_ID}" ]]; then
  echo "PROJECT_ID is required (e.g. project-dacd6b7b-dc96-4534-b82)." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

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

build_image "platform-control" "platform-control/Dockerfile.api" "platform-control-api"
build_image "platform-control" "platform-control/Dockerfile.worker" "platform-control-worker"
build_image "legal-search/api" "legal-search/api/Dockerfile" "legal-search-api"
build_image "document-intelligence" "document-intelligence/Dockerfile.runtime-ingress" "document-intelligence-ingress"

echo "Done. Built runtime images with tag: ${TAG}"
