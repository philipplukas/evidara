#!/usr/bin/env python3
"""Close the loop: push a completed RIS acquisition run through DI into legal-search.

Reads a completed run's bundle manifest from the local artifact store,
processes it through the document-intelligence pipeline, and forwards
the document.processed event to legal-search for OpenSearch indexing.

Prerequisites:
    - Platform-control API at http://localhost:8000 (for run metadata)
    - DI package installed (pip install -e document-intelligence)
    - Legal-search API at http://localhost:3001 (optional, for projection)
    - OpenSearch at http://localhost:9200 (optional, for verification)

Usage:
    python scripts/close-loop-ris.py --run-id <run_id> [--artifact-dir DIR]
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

_DEFAULT_PC_URL = "http://localhost:8000"
_DEFAULT_LS_URL = "http://localhost:3001"
_DEFAULT_OS_URL = "http://localhost:9200"
_DEFAULT_ARTIFACT_DIR = Path("platform-control/.data/raw-artifacts")


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _post_json(url: str, body: dict) -> dict | None:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8")
            return json.loads(text) if text.strip() else None
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        print(f"  HTTP {exc.code}: {error_body[:500]}", file=sys.stderr)
        raise


def find_bundle_event(run_dir: Path, run_id: str) -> dict[str, Any] | None:
    """Try to load the persisted bundle_event.json; fall back to reconstruction."""
    event_path = run_dir / "bundle_event.json"
    if event_path.exists():
        print(f"  Found persisted bundle event: {event_path}")
        return json.loads(event_path.read_text(encoding="utf-8"))
    return None


def find_bundle_manifest(run_dir: Path) -> tuple[str, dict[str, Any]] | None:
    """Find the bundle manifest JSON file in the run directory."""
    for path in run_dir.glob("abm_*.json"):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        return path.stem, manifest
    return None


def reconstruct_bundle_event(
    manifest_id: str, manifest: dict[str, Any], manifest_path: Path,
) -> dict[str, Any]:
    """Build an artifact_bundle.available event from the stored manifest."""
    from datetime import datetime, timezone
    provenance = manifest.get("provenance", {})
    manifest_bytes = manifest_path.read_bytes()

    import hashlib
    checksum = hashlib.sha256(manifest_bytes).hexdigest()

    return {
        "event_type": "artifact_bundle.available",
        "event_version": 1,
        "event_id": f"evt_reconstructed_{manifest_id}",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "producer": "platform-control",
        "correlation_id": provenance.get("run_id"),
        "payload": {
            "bundle_manifest_id": manifest_id,
            "source_snapshot_id": manifest.get("source_snapshot_id", ""),
            "provenance": provenance,
            "source_origin_kind": manifest.get("source_origin_kind", "official_primary"),
            "trust_tier": manifest.get("trust_tier", "authoritative"),
            "bundle_manifest_ref": {
                "manifest_id": manifest_id,
                "manifest_type": "artifact_bundle_manifest",
                "manifest_version": 1,
                "storage_ref": {
                    "uri": f"file://{manifest_path.resolve()}",
                    "content_type": "application/json",
                    "byte_size": len(manifest_bytes),
                    "checksum": checksum,
                    "checksum_algorithm": "sha256",
                    "created_at": manifest.get("snapshot_captured_at", ""),
                },
            },
        },
    }


def run_di_pipeline(event_data: dict[str, Any]) -> dict[str, Any]:
    """Process the bundle event through the DI pipeline and return the result."""
    try:
        from document_intelligence.ingest.loaders import (
            BundleLoader,
            LocalFilesystemBundleLoader,
            SelectedArtifactBundle,
        )
        from document_intelligence.contracts.envelope import (
            ArtifactBundleManifestArtifact,
            ManifestRef,
        )
        from document_intelligence.pipeline import ProcessingPipeline
    except ImportError:
        print("ERROR: document_intelligence package not installed.", file=sys.stderr)
        print("  Run: pip install -e document-intelligence", file=sys.stderr)
        sys.exit(1)

    class InlineBodyBundleLoader(BundleLoader):
        """Loader that extracts inline_body from JSON-wrapped artifact payloads."""

        def __init__(self) -> None:
            self._delegate = LocalFilesystemBundleLoader()

        def load_bundle(self, manifest_ref: ManifestRef) -> SelectedArtifactBundle:
            return self._delegate.load_bundle(manifest_ref)

        def read_artifact_text(self, artifact: ArtifactBundleManifestArtifact) -> str:
            uri = artifact.storage_ref.uri
            path = uri[len("file://"):] if uri.startswith("file://") else uri
            raw = Path(path).read_text(encoding="utf-8")
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                return raw
            if isinstance(data, dict) and "inline_body" in data:
                return data["inline_body"]
            return raw

    pipeline = ProcessingPipeline(bundle_loader=InlineBodyBundleLoader())
    result = pipeline.process_event(event_data)
    return {
        "document": result.document,
        "sections": result.sections,
        "manifest": result.manifest,
        "document_processed_event": result.document_processed_event,
        "status_events": result.status_events,
    }


def post_to_legal_search(event: dict[str, Any], ls_url: str) -> bool:
    """Forward the document.processed event to legal-search projections endpoint."""
    url = f"{ls_url}/v1/projections/events/document-processed"
    try:
        _post_json(url, event)
        return True
    except (HTTPError, URLError) as exc:
        print(f"  Legal-search POST failed: {exc}", file=sys.stderr)
        return False


def verify_opensearch(document_id: str, os_url: str) -> bool:
    """Check if the document landed in OpenSearch."""
    try:
        result = _get_json(
            f"{os_url}/documents-write/_search?q=document_id:{document_id}&size=1"
        )
        hits = result.get("hits", {}).get("total", {})
        total = hits.get("value", 0) if isinstance(hits, dict) else hits
        return int(total) > 0
    except (HTTPError, URLError):
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Close the RIS acquisition-to-search loop")
    parser.add_argument("--run-id", required=True, help="Completed run ID")
    parser.add_argument("--artifact-dir", type=Path, default=_DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--pc-url", default=_DEFAULT_PC_URL, help="Platform-control API URL")
    parser.add_argument("--ls-url", default=_DEFAULT_LS_URL, help="Legal-search API URL")
    parser.add_argument("--os-url", default=_DEFAULT_OS_URL, help="OpenSearch URL")
    parser.add_argument("--skip-legal-search", action="store_true", help="Skip legal-search POST")
    parser.add_argument("--skip-opensearch", action="store_true", help="Skip OpenSearch verify")
    args = parser.parse_args()

    run_id = args.run_id
    run_dir = args.artifact_dir / run_id

    print(f"=== Close the Loop: {run_id} ===\n")

    # Step 1: Verify run directory
    if not run_dir.is_dir():
        print(f"ERROR: Run directory not found: {run_dir}", file=sys.stderr)
        sys.exit(1)
    print(f"1. Run directory: {run_dir}")
    artifact_count = len(list(run_dir.glob("art_*.json")))
    print(f"   Artifacts on disk: {artifact_count}")

    # Step 2: Load or reconstruct the bundle event
    print("\n2. Loading bundle event...")
    bundle_event = find_bundle_event(run_dir, run_id)
    if bundle_event is None:
        manifest_result = find_bundle_manifest(run_dir)
        if manifest_result is None:
            print("ERROR: No bundle manifest (abm_*.json) found in run directory.", file=sys.stderr)
            sys.exit(1)
        manifest_id, manifest = manifest_result
        manifest_path = run_dir / f"{manifest_id}.json"
        print(f"  Reconstructing from manifest: {manifest_id}")
        bundle_event = reconstruct_bundle_event(manifest_id, manifest, manifest_path)

    print(f"  Event type: {bundle_event.get('event_type')}")
    print(f"  Bundle manifest: {bundle_event.get('payload', {}).get('bundle_manifest_id')}")

    # Step 3: Run DI pipeline
    print("\n3. Processing through document-intelligence...")
    di_result = run_di_pipeline(bundle_event)
    doc = di_result["document"]
    sections = di_result["sections"]
    doc_event = di_result["document_processed_event"]

    print(f"  Document ID: {doc.document_id}")
    print(f"  Title: {doc.title}")
    print(f"  Document type: {doc.document_type}")
    print(f"  Sections: {len(sections)}")
    print(f"  Full text length: {len(doc.full_text or '')} chars")
    if doc.metadata.get("source_flavor"):
        print(f"  Source flavor: {doc.metadata['source_flavor']}")
    citations = doc.extensions.get("citations", [])
    if citations:
        print(f"  Citations extracted: {len(citations)}")

    # Step 4: Forward to legal-search
    if not args.skip_legal_search:
        print(f"\n4. Forwarding to legal-search ({args.ls_url})...")
        success = post_to_legal_search(doc_event, args.ls_url)
        if success:
            print("  Projection accepted.")
        else:
            print("  Projection failed (legal-search may not be running).")
    else:
        print("\n4. Skipping legal-search (--skip-legal-search)")

    # Step 5: Verify in OpenSearch
    if not args.skip_legal_search and not args.skip_opensearch:
        print(f"\n5. Verifying in OpenSearch ({args.os_url})...")
        found = verify_opensearch(doc.document_id, args.os_url)
        if found:
            print(f"  FOUND in OpenSearch: {doc.document_id}")
        else:
            print(f"  NOT FOUND in OpenSearch (may need time to index)")
    else:
        print("\n5. Skipping OpenSearch verification")

    # Summary
    print(f"\n=== Summary ===")
    print(f"  Run:              {run_id}")
    print(f"  Document ID:      {doc.document_id}")
    print(f"  Title:            {doc.title}")
    print(f"  Sections:         {len(sections)}")
    print(f"  Text length:      {len(doc.full_text or '')} chars")
    print(f"  Processing:       OK")

    # Write the document.processed event to disk for debugging
    event_out = run_dir / "document_processed_event.json"
    event_out.write_text(json.dumps(doc_event, indent=2, default=str), encoding="utf-8")
    print(f"  Event saved:      {event_out}")


if __name__ == "__main__":
    main()
