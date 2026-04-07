#!/usr/bin/env python3
"""Bootstrap a RIS OGD acquisition run end-to-end.

Creates a Source + SourceVersion for Austrian federal law via the RIS OGD API,
approves the version, triggers a run, and optionally pipes the result through
the document-intelligence pipeline.

Prerequisites:
    1. Platform-control API running at http://localhost:8000
       (bash scripts/local-vertical-slice.sh up search && cd platform-control && uv run uvicorn ...)
    2. Reference data seeded (jurisdictions + authorities from hierarchies/)

Usage:
    python scripts/bootstrap-ris-source.py [--api-url URL] [--max-pages N] [--process-di]

Examples:
    # Quick smoke test: 1 page of results
    python scripts/bootstrap-ris-source.py --max-pages 1

    # Full pipeline including DI processing
    python scripts/bootstrap-ris-source.py --max-pages 1 --process-di
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from urllib import request
from urllib.error import HTTPError

_DEFAULT_API_URL = "http://localhost:8000"


def _post(url: str, body: dict, api_key: str | None = None) -> dict:
    data = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    req = request.Request(url, data=data, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        print(f"  HTTP {exc.code}: {error_body}", file=sys.stderr)
        raise


def _get(url: str, api_key: str | None = None) -> dict:
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key
    req = request.Request(url, headers=headers)
    with request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def create_source(api_url: str, api_key: str | None = None) -> str:
    print("1. Creating RIS AT Federal Law source...")
    body = {
        "name": "RIS AT Federal Law (OGD API)",
        "description": "Austrian federal legislation via OGD-RIS REST API",
        "jurisdiction_id": "jur_at_federal",
        "authority_id": "auth_ris",
        "source_type": "api",
        "document_family": "at_bundesrecht",
    }
    try:
        result = _post(f"{api_url}/v1/sources", body, api_key)
    except HTTPError:
        print("   (Source may already exist, trying to list...)")
        sources = _get(f"{api_url}/v1/sources", api_key)
        for src in sources.get("data", []):
            if src.get("authority_id") == "auth_ris" and src.get("document_family") == "at_bundesrecht":
                print(f"   Found existing source: {src['source_id']}")
                return src["source_id"]
        raise

    source_id = result["source_id"]
    print(f"   Source created: {source_id}")
    return source_id


def create_source_version(
    api_url: str,
    source_id: str,
    *,
    max_pages: int = 1,
    applikation: str | None = None,
    api_key: str | None = None,
) -> str:
    print(f"2. Creating SourceVersion (max_pages={max_pages})...")
    base_url = "https://data.bka.gv.at/ris/api/v2.6/Bundesrecht"

    body = {
        "version_label": "v1-ogd-test",
        "acquisition_spec": {
            "provider": "ris_ogd",
            "base_url": base_url,
            "preferred_formats": ["Xml", "Html"],
            "page_size": 5,
            "max_pages": max_pages,
            "tenant_id": "tenant_public",
            "corpus_id": "corpus_public_at_federal_law",
            "source_origin_kind": "official_primary",
            "trust_tier": "authoritative",
            "language_codes": ["de"],
            "document_type_hint": "statute",
            "max_content_bytes": 5000000,
        },
    }
    if applikation:
        body["acquisition_spec"]["applikation"] = applikation

    result = _post(f"{api_url}/v1/sources/{source_id}/versions", body, api_key)
    sv_id = result["source_version_id"]
    print(f"   SourceVersion created: {sv_id}")
    return sv_id


def approve_version(api_url: str, sv_id: str, api_key: str | None = None) -> None:
    print(f"3. Approving SourceVersion {sv_id}...")
    _post(f"{api_url}/v1/versions/{sv_id}/approve", {}, api_key)
    print("   Approved.")


def create_run(
    api_url: str, source_id: str, sv_id: str, api_key: str | None = None
) -> dict:
    print("4. Creating run (this triggers acquisition)...")
    body = {
        "source_id": source_id,
        "source_version_id": sv_id,
        "mode": "preview",
    }
    result = _post(f"{api_url}/v1/runs", body, api_key)
    run_id = result["run_id"]
    status = result["status"]
    artifacts_count = result.get("artifacts_count", 0)
    print(f"   Run: {run_id}  status={status}  artifacts={artifacts_count}")
    if result.get("failure_reason"):
        print(f"   FAILURE: {result['failure_reason']}")
    return result


def get_run_artifacts(api_url: str, run_id: str, api_key: str | None = None) -> list[dict]:
    result = _get(f"{api_url}/v1/runs/{run_id}/raw-artifacts", api_key)
    return result.get("data", [])


def process_with_di(run_result: dict, api_url: str, api_key: str | None = None) -> None:
    """Attempt to process the run's bundle event through the DI pipeline."""
    run_id = run_result["run_id"]
    print(f"\n5. Processing run {run_id} through document-intelligence...")

    artifacts = get_run_artifacts(api_url, run_id, api_key)
    if not artifacts:
        print("   No artifacts to process.")
        return

    print(f"   Found {len(artifacts)} raw artifacts.")
    print("   (DI processing requires the document-intelligence package installed)")
    print("   To process manually:")
    print(f"     curl {api_url}/v1/runs/{run_id}/raw-artifacts | python -m json.tool")
    print("     # Then pipe artifact_bundle.available event to:")
    print("     python -m document_intelligence.jobs.process_event <event.json>")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap a RIS OGD acquisition run")
    parser.add_argument("--api-url", default=_DEFAULT_API_URL, help="Platform-control API URL")
    parser.add_argument("--api-key", default=None, help="API key for protected routes")
    parser.add_argument("--max-pages", type=int, default=1, help="Max OGD API pages to fetch")
    parser.add_argument("--applikation", default=None, help="OGD Applikation filter (e.g. Vfgh, BrKons)")
    parser.add_argument("--process-di", action="store_true", help="Attempt DI processing after acquisition")
    args = parser.parse_args()

    print(f"=== RIS OGD Bootstrap (api={args.api_url}, max_pages={args.max_pages}) ===\n")

    source_id = create_source(args.api_url, args.api_key)
    sv_id = create_source_version(
        args.api_url,
        source_id,
        max_pages=args.max_pages,
        applikation=args.applikation,
        api_key=args.api_key,
    )
    approve_version(args.api_url, sv_id, args.api_key)
    run_result = create_run(args.api_url, source_id, sv_id, args.api_key)

    if run_result["status"] == "completed":
        print(f"\nRun completed successfully with {run_result.get('artifacts_count', 0)} artifacts.")
    elif run_result["status"] == "failed":
        print(f"\nRun FAILED: {run_result.get('failure_reason', 'unknown')}", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"\nRun status: {run_result['status']} (may still be processing)")

    if args.process_di:
        process_with_di(run_result, args.api_url, args.api_key)

    print("\n=== Done ===")
    print(f"Source:        {source_id}")
    print(f"SourceVersion: {sv_id}")
    print(f"Run:           {run_result['run_id']}")
    print(f"Status:        {run_result['status']}")
    print(f"Artifacts:     {run_result.get('artifacts_count', 0)}")


if __name__ == "__main__":
    main()
