"""Replay platform-control local outbox bundle events into DI and legal-search."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from document_intelligence.config.runtime import RuntimeSettings
from document_intelligence.processing_runtime import process_artifact_bundle_event_result

DEFAULT_OUTBOX_DIR = "/var/lib/evidara/raw-artifacts/event-outbox"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay platform-control local outbox artifact_bundle.available events."
    )
    parser.add_argument(
        "--outbox-dir",
        default=os.environ.get("DI_LOCAL_OUTBOX_DIR", DEFAULT_OUTBOX_DIR),
        help=f"Local outbox root (default: {DEFAULT_OUTBOX_DIR}).",
    )
    parser.add_argument(
        "--legal-search-api-url",
        default=os.environ.get("LEGAL_SEARCH_API_URL") or os.environ.get("NEXT_PUBLIC_API_URL"),
        help="legal-search API base URL used for projection events.",
    )
    parser.add_argument(
        "--legal-search-token",
        default=os.environ.get("LEGAL_SEARCH_API_TOKEN") or os.environ.get("EVIDARA_LEGAL_SEARCH_TOKEN"),
        help="Optional bearer token for legal-search projection endpoints.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Maximum bundle events to replay.")
    parser.add_argument(
        "--keep-projections",
        action="store_true",
        help="Leave replayed legal-search projections visible for manual evidence capture.",
    )
    parser.add_argument(
        "--withdraw-only",
        action="store_true",
        help="Withdraw replay projections recorded in processed markers without reprocessing bundles.",
    )
    args = parser.parse_args(argv)

    outbox = Path(args.outbox_dir)
    if not args.legal_search_api_url:
        print("legal-search API URL is required", file=sys.stderr)
        return 2

    replayer = LocalOutboxReplayer(
        outbox_dir=outbox,
        legal_search_api_url=str(args.legal_search_api_url),
        legal_search_token=args.legal_search_token,
    )
    try:
        if args.withdraw_only:
            summary = replayer.withdraw_marked_projections(limit=args.limit)
        else:
            summary = replayer.replay(limit=args.limit, keep_projections=args.keep_projections)
    except Exception as exc:
        print(f"local outbox replay failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if summary.get("status") == "failed" else 0


class LocalOutboxReplayer:
    def __init__(
        self,
        *,
        outbox_dir: Path,
        legal_search_api_url: str,
        legal_search_token: str | None = None,
    ) -> None:
        self.outbox_dir = outbox_dir
        self.legal_search_api_url = legal_search_api_url.rstrip("/")
        self.legal_search_token = legal_search_token
        self.bundle_dir = outbox_dir / "artifact-bundle-available"
        self.processed_dir = outbox_dir / "processed"
        self.failed_dir = outbox_dir / "failed"

    def replay(self, *, limit: int = 0, keep_projections: bool = False) -> dict[str, Any]:
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.failed_dir.mkdir(parents=True, exist_ok=True)
        events = self._pending_bundle_event_paths(limit=limit)
        records: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []

        for event_path in events:
            try:
                record = self._replay_event(event_path, keep_projections=keep_projections)
                records.append(record)
            except Exception as exc:
                failure = self._record_failure(event_path, exc)
                failures.append(failure)

        return {
            "status": "completed" if not failures else "failed",
            "outbox_dir": str(self.outbox_dir),
            "processed": len(records),
            "failed": len(failures),
            "records": records,
            "failures": failures,
        }

    def withdraw_marked_projections(self, *, limit: int = 0) -> dict[str, Any]:
        marker_paths = sorted(self.processed_dir.glob("*.json"))
        if limit > 0:
            marker_paths = marker_paths[:limit]

        records: list[dict[str, Any]] = []
        for marker_path in marker_paths:
            marker = _read_json(marker_path)
            # "quarantined" markers never produced a projection, so there is nothing to
            # withdraw and no `document_processed_event` to build a withdrawal from.
            if marker.get("cleanup_status") in {"withdrawn", "quarantined"}:
                continue
            withdrawal = self._withdraw_projection(marker)
            marker.update(withdrawal)
            _write_json_atomic(marker_path, marker)
            records.append(marker)

        return {
            "status": "completed",
            "outbox_dir": str(self.outbox_dir),
            "withdrawn": len(records),
            "records": records,
        }

    def _pending_bundle_event_paths(self, *, limit: int) -> list[Path]:
        if not self.bundle_dir.exists():
            return []
        paths = []
        for path in sorted(self.bundle_dir.glob("*.json")):
            if not (self.processed_dir / path.name).exists():
                paths.append(path)
        if limit > 0:
            return paths[:limit]
        return paths

    def _replay_event(self, event_path: Path, *, keep_projections: bool) -> dict[str, Any]:
        event = _read_json(event_path)
        result = process_artifact_bundle_event_result(
            event,
            runtime_settings=RuntimeSettings.from_environment(),
            require_surface_uris=True,
        )
        if result.is_quarantined:
            # Nothing was published to canonical, so there is no projection to post and
            # none to withdraw afterwards. The marker records *why*, so a replay sweep
            # over a quarantined cohort reads as a cohort, not as a silent gap (ADR-0047).
            marker = {
                "event_id": event["event_id"],
                "source_event_path": str(event_path),
                "bundle_manifest_id": event["payload"]["bundle_manifest_id"],
                "processing_manifest_id": result.manifest.processing_manifest_id,
                "source_url": _source_url_for_event(event),
                "quarantine": dict(result.quarantine or {}),
                "cleanup_status": "quarantined",
                "processed_at": _utc_now(),
            }
            _write_json_atomic(_marker_path(self.processed_dir, str(event["event_id"])), marker)
            return marker

        processed_event = result.document_processed_event
        assert result.document is not None  # guaranteed: not quarantined ⇒ a document was published
        projection_response = self._post_projection("document-processed", processed_event)
        marker = {
            "event_id": event["event_id"],
            "source_event_path": str(event_path),
            "bundle_manifest_id": event["payload"]["bundle_manifest_id"],
            "document_id": result.document.document_id,
            "document_revision": result.document.document_revision,
            "processing_manifest_id": result.manifest.processing_manifest_id,
            "title": result.document.title,
            "source_url": _source_url_for_event(event),
            "projection_response": projection_response,
            "document_processed_event": processed_event,
            "cleanup_status": "kept" if keep_projections else "pending",
            "processed_at": _utc_now(),
        }
        if not keep_projections:
            marker.update(self._withdraw_projection(marker))
        _write_json_atomic(_marker_path(self.processed_dir, str(event["event_id"])), marker)
        return marker

    def _withdraw_projection(self, marker: dict[str, Any]) -> dict[str, Any]:
        processed_event = marker["document_processed_event"]
        withdrawal_event = build_document_withdrawn_event(processed_event)
        response = self._post_projection("document-withdrawn", withdrawal_event)
        return {
            "cleanup_status": "withdrawn",
            "withdrawal_response": response,
            "document_withdrawn_event": withdrawal_event,
            "withdrawn_at": _utc_now(),
        }

    def _post_projection(self, endpoint: str, event: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.legal_search_api_url}/v1/projections/events/{endpoint}"
        return _post_json(url, event, token=self.legal_search_token)

    def _record_failure(self, event_path: Path, exc: Exception) -> dict[str, Any]:
        try:
            event = _read_json(event_path)
            event_id = str(event.get("event_id") or event_path.stem)
        except Exception:
            event_id = event_path.stem
        failure = {
            "event_id": event_id,
            "source_event_path": str(event_path),
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "failed_at": _utc_now(),
        }
        _write_json_atomic(_marker_path(self.failed_dir, event_id), failure)
        return failure


def build_document_withdrawn_event(processed_event: dict[str, Any]) -> dict[str, Any]:
    payload = processed_event["payload"]
    document_id = payload["document_id"]
    now = _utc_now()
    return {
        "event_type": "document.withdrawn",
        "event_version": 1,
        "event_id": f"evt_local_outbox_withdraw_{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}",
        "occurred_at": now,
        "producer": "document-intelligence",
        "correlation_id": processed_event.get("correlation_id") or payload["provenance"]["run_id"],
        "payload": {
            "document_id": document_id,
            "document_revision": payload["document_revision"],
            "processing_manifest_id": payload["processing_manifest_id"],
            "provenance": payload["provenance"],
            "reason_code": "operator_withdrawn",
            "reason_summary": "Internal beta replay proof cleanup.",
            "search_disposition": "remove",
        },
    }


def _post_json(url: str, payload: dict[str, Any], *, token: str | None) -> dict[str, Any]:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, sort_keys=True).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"POST {url} failed with {exc.code}: {body}") from exc


def _source_url_for_event(event: dict[str, Any]) -> str | None:
    storage_ref = event.get("payload", {}).get("bundle_manifest_ref", {}).get("storage_ref", {})
    uri = storage_ref.get("uri") if isinstance(storage_ref, dict) else None
    if not isinstance(uri, str):
        return None
    if uri.startswith("file://"):
        manifest_path = Path(uri.removeprefix("file://"))
    else:
        manifest_path = Path(uri)
    try:
        manifest = _read_json(manifest_path)
    except Exception:
        return None
    upstream_locator = manifest.get("upstream_locator")
    return upstream_locator if isinstance(upstream_locator, str) else None


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def _marker_path(directory: Path, event_id: str) -> Path:
    if not event_id or "/" in event_id or "\\" in event_id or event_id in {".", ".."}:
        raise ValueError(f"unsafe event_id for marker path: {event_id!r}")
    return directory / f"{event_id}.json"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
