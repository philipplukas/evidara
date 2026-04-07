from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from platform_control.config import Settings

EnqueueOutcome = Literal["enqueued", "duplicate", "skipped_not_configured", "failed"]


@dataclass(slots=True)
class ArgillaEnqueueResult:
    outcome: EnqueueOutcome
    detail: str | None = None


def _records_url(settings: Settings) -> str | None:
    if not settings.argilla_api_base_url or not settings.argilla_dataset_id:
        return None
    base = str(settings.argilla_api_base_url).rstrip("/")
    path = settings.argilla_records_path.format(dataset_id=settings.argilla_dataset_id)
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"


def build_argilla_record_body(task_payload: dict[str, Any], *, external_id: str) -> dict[str, Any]:
    """Shape aligned with docs/runbooks/argilla-review-routing-and-sync.md."""
    metadata = dict(task_payload.get("metadata") or {})
    fields = dict(task_payload.get("fields") or {})
    suggestions = task_payload.get("suggestions")
    guidelines = task_payload.get("guidelines")
    body: dict[str, Any] = {
        "external_id": external_id,
        "metadata": metadata,
        "fields": fields,
    }
    if suggestions is not None:
        body["suggestions"] = suggestions
    if guidelines is not None:
        body["guidelines"] = guidelines
    return body


class ArgillaEnqueueService:
    """POST review tasks to Argilla HTTP API (or report skip when not configured)."""

    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._client = client

    def is_configured(self) -> bool:
        s = self._settings
        return bool(s.argilla_api_base_url and s.argilla_api_key and s.argilla_dataset_id)

    async def enqueue_record(
        self,
        *,
        external_id: str,
        task_payload: dict[str, Any],
        idempotency_key: str,
    ) -> ArgillaEnqueueResult:
        if not self.is_configured():
            return ArgillaEnqueueResult(
                outcome="skipped_not_configured",
                detail="Set PLATFORM_CONTROL_ARGILLA_API_BASE_URL, _API_KEY, and _DATASET_ID.",
            )

        url = _records_url(self._settings)
        if url is None:
            return ArgillaEnqueueResult(
                outcome="skipped_not_configured",
                detail="Missing URL parts.",
            )

        record = build_argilla_record_body(task_payload, external_id=external_id)
        bulk_body = {"records": [record]}

        headers = {
            "X-Argilla-API-Key": self._settings.argilla_api_key or "",
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
        }

        timeout = httpx.Timeout(self._settings.argilla_http_timeout_seconds)
        own_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=timeout)
        try:
            try:
                response = await client.post(url, headers=headers, content=json.dumps(bulk_body))
            except httpx.HTTPError as exc:
                return ArgillaEnqueueResult(outcome="failed", detail=str(exc))

            if response.status_code >= 400:
                return ArgillaEnqueueResult(
                    outcome="failed",
                    detail=f"HTTP {response.status_code}: {response.text[:500]}",
                )
            return ArgillaEnqueueResult(outcome="enqueued", detail=None)
        finally:
            if own_client:
                await client.aclose()
