"""``pc fetch --record PATH`` — capture a live provider run as a cassette.

Dispatches the configured provider against the real network exactly once, then
serialises its inline resources (plus provider request/response payloads) into
a JSON cassette keyed by ``source_version_id``. A subsequent run of the same
version with ``execution_mode=shadow`` replays that cassette offline.

Only providers that return ``inline_resources`` on ``start_run`` are
usefully recordable this way (deterministic_http, fedlex_sparql, ris_ogd).
Firecrawl's async webhook flow needs a different recorder — fetch warns but
still writes the job-creation response so operators can tell what happened.
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
                "the crawl results come via webhook and need a separate recorder.",
                file=sys.stderr,
            )
        path, result = await record_cassette(
            session=session,
            provider=provider,
            source_version_id=namespace.source_version_id,
            cassette_dir=cassette_dir,
        )

    print(
        f"recorded {len(result.inline_resources)} resource(s) from "
        f"{result.provider} to {path}"
    )
    return 0


__all__ = ["record_cassette", "run_from_args"]
