"""``pc ingest --from-fixture PATH`` — replay a Firecrawl webhook payload offline.

Feeds a recorded ``WebhookReceipt``-shaped payload (or list of payloads) directly
into :meth:`FirecrawlWebhookService.process_payload`, bypassing the HTTP handler
and the webhook signature check. Enables fixture-driven iteration on the ingest
side without the upstream Firecrawl service.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from platform_control.errors import WebhookRetryableError
from platform_control.services.firecrawl_webhook_service import FirecrawlWebhookService


def load_payloads(path: Path) -> list[dict[str, Any]]:
    """Return one or more Firecrawl-shaped webhook payloads from a JSON fixture."""
    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    if isinstance(raw, list):
        if not all(isinstance(entry, dict) for entry in raw):
            raise ValueError(f"Fixture {path} must contain dicts or a dict-of-dicts; got mixed.")
        return raw
    if isinstance(raw, dict):
        return [raw]
    raise ValueError(f"Fixture {path} must contain a JSON object or array of objects.")


async def ingest_payloads(
    payloads: list[dict[str, Any]],
    *,
    service: FirecrawlWebhookService,
) -> int:
    """Drive each payload through ``process_payload``. Returns the number processed."""
    for payload in payloads:
        await service.process_payload(payload)
    return len(payloads)


async def run_from_args(namespace: argparse.Namespace) -> int:
    # Imported lazily: ``integrations`` transitively loads ``services.__init__``
    # which imports ``run_service``; doing it at module scope would create a
    # circular import when ``cli/ingest.py`` itself loads before ``integrations``.
    from platform_control.config import get_settings
    from platform_control.database import get_session_maker
    from platform_control.integrations import get_artifact_store, get_raw_artifact_publisher

    fixture_path = Path(namespace.from_fixture).expanduser().resolve()
    if not fixture_path.exists():
        print(f"Fixture not found: {fixture_path}", file=sys.stderr)
        return 2
    payloads = load_payloads(fixture_path)

    settings = get_settings()
    session_maker = get_session_maker()
    artifact_store = get_artifact_store(settings)
    publisher = get_raw_artifact_publisher(settings)

    async with session_maker() as session:
        service = FirecrawlWebhookService(
            session=session,
            artifact_store=artifact_store,
            publisher=publisher,
            # Signature verification is bypassed here; process_payload is the pure
            # entrypoint that does not call _verify_signature.
            webhook_secret=settings.firecrawl_webhook_secret,
        )
        try:
            processed = await ingest_payloads(payloads, service=service)
        except WebhookRetryableError as exc:
            # The fixture references a crawl this database knows nothing about — replaying
            # it applies to nothing. Fail loudly rather than reporting a clean ingest.
            print(f"ingest failed: {exc}", file=sys.stderr)
            return 1

    print(f"processed {processed} payload(s) from {fixture_path}")
    return 0


__all__ = ["load_payloads", "ingest_payloads", "run_from_args"]
