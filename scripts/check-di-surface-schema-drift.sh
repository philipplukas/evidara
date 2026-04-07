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
SURFACE_DEFINITIONS_FILE="${SURFACE_DEFINITIONS_FILE:-document-intelligence/src/document_intelligence/persist/surfaces.py}"

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
    --surface-definitions-file)
      SURFACE_DEFINITIONS_FILE="${2:?missing value for --surface-definitions-file}"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: $0 [--project PROJECT_ID] [--surfaces-root-uri gs://bucket/published] [--surface-definitions-file path]" >&2
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

if [[ ! -f "${SURFACE_DEFINITIONS_FILE}" ]]; then
  echo "Surface definitions file not found: ${SURFACE_DEFINITIONS_FILE}" >&2
  exit 1
fi

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud CLI is required for schema drift check." >&2
  exit 1
fi

echo "Checking DI published surface schema drift..."
echo "  project: ${PROJECT_ID}"
echo "  root:    ${SURFACES_ROOT_URI}"
echo "  defs:    ${SURFACE_DEFINITIONS_FILE}"

PROJECT_ID="${PROJECT_ID}" SURFACES_ROOT_URI="${SURFACES_ROOT_URI}" SURFACE_DEFINITIONS_FILE="${SURFACE_DEFINITIONS_FILE}" python3 - <<'PY'
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys

project_id = os.environ["PROJECT_ID"]
surfaces_root_uri = os.environ["SURFACES_ROOT_URI"].rstrip("/")
surface_definitions_file = os.environ["SURFACE_DEFINITIONS_FILE"]


def load_surface_columns(path: str) -> dict[str, dict[str, list[str]]]:
    source = open(path, "r", encoding="utf-8").read()
    tree = ast.parse(source, filename=path)

    surface_var_to_name: dict[str, str] = {}
    columns_by_var: dict[str, dict[str, list[str]]] = {}

    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if not isinstance(call.func, ast.Name) or call.func.id != "PublishedSurfaceDefinition":
            continue
        var_name = target.id
        surface_name = None
        for kw in call.keywords:
            if kw.arg == "surface_name" and isinstance(kw.value, ast.Constant) and isinstance(
                kw.value.value, str
            ):
                surface_name = kw.value.value
                break
        if not surface_name:
            continue
        surface_var_to_name[var_name] = surface_name
        columns_by_var[var_name] = {"required": [], "optional": []}

        for kw in call.keywords:
            if kw.arg != "columns" or not isinstance(kw.value, ast.Tuple):
                continue
            for elt in kw.value.elts:
                if not isinstance(elt, ast.Call):
                    continue
                if not isinstance(elt.func, ast.Name) or elt.func.id != "SurfaceColumn":
                    continue
                if len(elt.args) < 3:
                    continue
                name_node = elt.args[0]
                nullable_node = elt.args[2]
                if not isinstance(name_node, ast.Constant) or not isinstance(name_node.value, str):
                    continue
                if not isinstance(nullable_node, ast.Constant) or not isinstance(
                    nullable_node.value, bool
                ):
                    continue
                if nullable_node.value:
                    columns_by_var[var_name]["optional"].append(name_node.value)
                else:
                    columns_by_var[var_name]["required"].append(name_node.value)

    result: dict[str, dict[str, list[str]]] = {}
    for var_name, surface_name in surface_var_to_name.items():
        result[surface_name] = columns_by_var[var_name]
    return result


SURFACE_COLUMNS = load_surface_columns(surface_definitions_file)
if not SURFACE_COLUMNS:
    print(
        f"Failed to parse surface definitions from {surface_definitions_file}.",
        file=sys.stderr,
    )
    sys.exit(1)


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
