#!/usr/bin/env bash
set -euo pipefail

# Fail-fast preflight check for DI published Delta surface schema drift.
# Compares live Delta table schemas in GCS against canonical surface
# definitions in document_intelligence.persist.surfaces.
#
# Usage:
#   ./scripts/check-di-surface-schema-drift.sh \
#     --project project-id \
#     --surfaces-root-uri gs://bucket/published
#
# Environment fallback:
#   PROJECT_ID / GCP_PROJECT_ID
#   DI_SURFACES_ROOT_URI

PROJECT_ID="${PROJECT_ID:-${GCP_PROJECT_ID:-}}"
SURFACES_ROOT_URI="${DI_SURFACES_ROOT_URI:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      PROJECT_ID="${2:?missing value for --project}"
      shift 2
      ;;
    --surfaces-root-uri)
      SURFACES_ROOT_URI="${2:?missing value for --surfaces-root-uri}"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: $0 [--project PROJECT_ID] [--surfaces-root-uri gs://bucket/published]" >&2
      exit 1
      ;;
  esac
done

if [[ -z "${PROJECT_ID}" ]]; then
  echo "PROJECT_ID is required (use --project or set PROJECT_ID/GCP_PROJECT_ID)." >&2
  exit 1
fi

if [[ -z "${SURFACES_ROOT_URI}" ]]; then
  echo "DI_SURFACES_ROOT_URI is required (use --surfaces-root-uri or set DI_SURFACES_ROOT_URI)." >&2
  exit 1
fi

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud CLI is required for schema drift check." >&2
  exit 1
fi

echo "Checking DI published surface schema drift..."
echo "  project: ${PROJECT_ID}"
echo "  root:    ${SURFACES_ROOT_URI}"

PROJECT_ID="${PROJECT_ID}" SURFACES_ROOT_URI="${SURFACES_ROOT_URI}" python3 - <<'PY'
from __future__ import annotations

import json
import os
import subprocess
import sys

project_id = os.environ["PROJECT_ID"]
surfaces_root_uri = os.environ["SURFACES_ROOT_URI"].rstrip("/")

SURFACE_COLUMNS = {
    "published_documents": {
        "required": [
        "document_id",
        "document_revision",
        "processing_manifest_id",
        "provenance",
        "primary_artifact_id",
        "title",
        "processed_at",
        "processing_version",
        "lifecycle_status",
        "full_text",
        "body_text",
    ],
        "optional": [
            "jurisdiction_id",
            "authority_id",
            "document_type",
            "effective_date",
            "metadata",
            "extensions",
        ],
    },
    "published_sections": {
        "required": [
        "section_id",
        "document_id",
        "document_revision",
        "processing_manifest_id",
        "provenance",
        "ordinal",
        "depth",
        "content",
    ],
        "optional": [
            "parent_section_id",
            "title",
            "section_type",
            "metadata",
        ],
    },
    "processing_manifests": {
        "required": [
        "processing_manifest_id",
        "manifest_version",
        "document_id",
        "document_revision",
        "processing_version",
        "status",
        "provenance",
        "input_bundle_manifest_ref",
        "selected_profiles",
        "document_count",
        "section_count",
        "citation_count",
    ],
        "optional": [
            "reference_snapshot_set_ref",
            "published_document_ref",
            "published_sections_ref",
            "canonical_ready_at",
            "supersedes_processing_manifest_id",
            "failure",
        ],
    },
}


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def list_delta_logs(surface_name: str) -> list[str]:
    uri = f"{surfaces_root_uri}/{surface_name}/_delta_log/*.json"
    proc = _run(["gcloud", "storage", "ls", uri, "--project", project_id])
    if proc.returncode != 0:
        if "One or more URLs matched no objects" in proc.stderr:
            return []
        raise RuntimeError(
            f"Failed to list Delta logs for {surface_name}: {proc.stderr.strip() or proc.stdout.strip()}"
        )
    return sorted((line.strip() for line in proc.stdout.splitlines() if line.strip()), reverse=True)


def extract_latest_metadata_schema(log_paths: list[str]) -> str | None:
    for path in log_paths:
        proc = _run(["gcloud", "storage", "cat", path, "--project", project_id])
        if proc.returncode != 0:
            raise RuntimeError(
                f"Failed to read Delta log {path}: {proc.stderr.strip() or proc.stdout.strip()}"
            )
        for raw_line in proc.stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            metadata = payload.get("metaData")
            if isinstance(metadata, dict):
                schema = metadata.get("schemaString")
                if isinstance(schema, str) and schema.strip():
                    return schema
    return None


def field_names_from_schema_string(schema_string: str) -> list[str]:
    schema = json.loads(schema_string)
    fields = schema.get("fields")
    if not isinstance(fields, list):
        raise RuntimeError("Invalid Delta schema string: missing fields array")
    names: list[str] = []
    for field in fields:
        if isinstance(field, dict) and isinstance(field.get("name"), str):
            names.append(field["name"])
    return names


drift_found = False
for surface_name, columns in SURFACE_COLUMNS.items():
    required = columns["required"]
    optional = columns["optional"]
    expected_all = required + optional
    logs = list_delta_logs(surface_name)
    if not logs:
        print(
            f"[WARN] {surface_name}: no Delta logs found under {surfaces_root_uri}. "
            "Skipping (surface not initialized yet)."
        )
        continue
    schema_string = extract_latest_metadata_schema(logs)
    if schema_string is None:
        print(
            f"[FAIL] {surface_name}: unable to locate metadata schema in Delta logs.",
            file=sys.stderr,
        )
        drift_found = True
        continue
    actual = field_names_from_schema_string(schema_string)
    missing_required = [name for name in required if name not in actual]
    missing_optional = [name for name in optional if name not in actual]
    extra = [name for name in actual if name not in expected_all]
    if missing_required or extra:
        print(f"[FAIL] {surface_name}: schema drift detected.", file=sys.stderr)
        print(f"  expected required: {required}", file=sys.stderr)
        print(f"  actual:   {actual}", file=sys.stderr)
        if missing_required:
            print(f"  missing required: {missing_required}", file=sys.stderr)
        if extra:
            print(f"  extra:    {extra}", file=sys.stderr)
        drift_found = True
    else:
        print(
            f"[OK]   {surface_name}: required schema columns present "
            f"({len(required)}/{len(required)})."
        )
        if missing_optional:
            print(
                f"[WARN] {surface_name}: optional columns currently absent: {missing_optional}. "
                "This can later cause write failures when those fields become populated."
            )

if drift_found:
    print("", file=sys.stderr)
    print("Remediation (dev only):", file=sys.stderr)
    print(f'  gcloud storage rm --recursive "{surfaces_root_uri}/**"', file=sys.stderr)
    print(
        "  Then rerun smoke: GCP_PROJECT_ID=<project> SMOKE_SEED_URL=http://example.org "
        "SMOKE_REQUEST_TIMEOUT_SECONDS=10 scripts/e2e-smoke-test.sh --env dev",
        file=sys.stderr,
    )
    sys.exit(2)

print("DI surface schema drift check passed.")
PY
