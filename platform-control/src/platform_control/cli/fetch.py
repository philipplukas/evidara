"""``pc fetch`` — cassette recording and webhook-log bundling.

Two modes:

- ``pc fetch <source_version_id> [--record PATH]``: dispatches the configured
  provider against the real network exactly once and serialises its inline
  resources into a JSON cassette keyed by ``source_version_id``. A subsequent
  run of the same version with ``execution_mode=shadow`` replays that cassette
  offline.

- ``pc fetch --from-webhook-log DIR [--out PATH]``: walks a directory of
  recorded Firecrawl webhook payloads (populated by the webhook recorder when
  ``PLATFORM_CONTROL_FIRECRAWL_WEBHOOK_RECORD_DIR`` is set) and emits a single
  JSON fixture that ``pc ingest --from-fixture`` can replay in one shot.

Only providers that return ``inline_resources`` on ``start_run`` are
usefully recordable via ``--record`` (deterministic_http, fedlex_sparql,
ris_ogd). Firecrawl's async webhook flow uses ``--from-webhook-log`` instead.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_control.domain import ExecutionMode, RunMode, RunStatus
from platform_control.errors import NotFoundError
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.services.acquisition_provider import (
    AcquisitionProvider,
    ProviderStartResult,
)


def bundle_webhook_log(src_dir: Path) -> list[dict[str, Any]]:
    """Walk ``src_dir`` recursively and return all JSON payloads in sorted order.

    The webhook recorder writes one payload per file with a timestamp prefix,
    so lexicographic sort by path is a reasonable approximation of arrival
    order. Callers that care about strict chronology can re-order by
    ``payload['received_at']`` — the file names already encode a UTC timestamp
    so lexicographic order matches time order when receivers don't clock-skew.

    Raises :class:`FileNotFoundError` when the directory does not exist.
    """
    if not src_dir.exists():
        raise FileNotFoundError(f"Webhook log directory not found: {src_dir}")
    payloads: list[dict[str, Any]] = []
    for path in sorted(src_dir.rglob("*.json")):
        if not path.is_file():
            continue
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError(
                f"Webhook log entry at {path} is not a JSON object; refusing to bundle."
            )
        payloads.append(data)
    return payloads


def write_bundle(payloads: list[dict[str, Any]], out_path: Path) -> Path:
    """Serialise ``payloads`` as a JSON array that ``pc ingest --from-fixture`` accepts."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payloads, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return out_path


async def record_cassette(
    *,
    session: AsyncSession,
    provider: AcquisitionProvider,
    source_version_id: str,
    cassette_dir: Path,
) -> tuple[Path, ProviderStartResult]:
    """Invoke ``provider.start_run`` once and persist its output as a cassette.

    Pure seam so unit tests can drive a fake provider. The ``Run`` used here is
    ephemeral — not added to the session — because ``pc fetch --record`` is a
    dev helper, not a production dispatch path.
    """
    source_version = await session.get(SourceVersion, source_version_id)
    if source_version is None:
        raise NotFoundError(f"SourceVersion not found: {source_version_id}")
    if source_version.execution_mode is ExecutionMode.SHADOW:
        raise ValueError(
            f"SourceVersion {source_version_id} is in shadow mode; record against a "
            "live version before promoting it."
        )
    source = await session.get(Source, source_version.source_id)
    if source is None:
        raise NotFoundError(f"Source not found: {source_version.source_id}")

    ephemeral_run = Run(
        run_id=f"rec_{source_version_id}_{int(datetime.now(UTC).timestamp())}",
        source_id=source.source_id,
        source_version_id=source_version.source_version_id,
        mode=RunMode.PREVIEW,
        status=RunStatus.PENDING,
    )
    result = await provider.start_run(source, source_version, ephemeral_run)

    cassette_dir.mkdir(parents=True, exist_ok=True)
    cassette_path = cassette_dir / f"{source_version_id}.json"
    cassette_path.write_text(
        json.dumps(_serialise_result(result), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return cassette_path, result


def _serialise_result(result: ProviderStartResult) -> dict[str, Any]:
    return {
        "provider_name": result.provider,
        "recorded_at": datetime.now(UTC).isoformat(),
        "request_payload": result.request_payload,
        "response_payload": result.response_payload,
        "inline_failure_reason": result.inline_failure_reason,
        "inline_resources": [asdict(resource) for resource in result.inline_resources],
    }


async def run_from_args(namespace: argparse.Namespace) -> int:
    from platform_control.config import get_settings
    from platform_control.database import get_session_maker
    from platform_control.services.provider_registry_factory import build_provider_registry

    # Webhook-log bundling mode: no DB, no provider. Just walks a directory
    # of recorded payloads and writes a single replayable fixture.
    webhook_log_source = getattr(namespace, "from_webhook_log", None)
    if webhook_log_source:
        src_dir = Path(webhook_log_source).expanduser().resolve()
        out_path = (
            Path(namespace.out).expanduser().resolve()
            if getattr(namespace, "out", None)
            else src_dir.with_suffix(".bundle.json")
        )
        try:
            payloads = bundle_webhook_log(src_dir)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        write_bundle(payloads, out_path)
        print(f"bundled {len(payloads)} payload(s) from {src_dir} -> {out_path}")
        return 0

    # Recording mode: dispatch a provider and persist inline_resources.
    if not getattr(namespace, "source_version_id", None):
        print(
            "pc fetch requires either a source_version_id (record mode) or "
            "--from-webhook-log DIR (bundle mode).",
            file=sys.stderr,
        )
        return 2

    settings = get_settings()
    session_maker: async_sessionmaker[AsyncSession] = get_session_maker()
    registry = build_provider_registry(settings)

    cassette_dir = (
        Path(namespace.cassette_dir).expanduser().resolve()
        if namespace.cassette_dir
        else settings.cassette_dir
    )

    async with session_maker() as session:
        source_version = await session.get(SourceVersion, namespace.source_version_id)
        if source_version is None:
            print(f"SourceVersion not found: {namespace.source_version_id}", file=sys.stderr)
            return 2
        if source_version.execution_mode is ExecutionMode.SHADOW:
            print(
                f"SourceVersion {namespace.source_version_id} is in shadow mode; "
                "record against a live version before promoting it.",
                file=sys.stderr,
            )
            return 2
        provider = registry.resolve_for_version(source_version)
        if provider.provider_name == "firecrawl":
            print(
                "warning: firecrawl records only the job-creation response; "
                "use --from-webhook-log against the webhook record dir instead.",
                file=sys.stderr,
            )
        path, result = await record_cassette(
            session=session,
            provider=provider,
            source_version_id=namespace.source_version_id,
            cassette_dir=cassette_dir,
        )

    print(f"recorded {len(result.inline_resources)} resource(s) from {result.provider} to {path}")
    return 0


__all__ = [
    "bundle_webhook_log",
    "record_cassette",
    "run_from_args",
    "write_bundle",
]
