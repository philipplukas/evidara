"""Cassette-backed acquisition provider for shadow-mode and fixture-driven runs.

Reads a JSON cassette keyed by ``SourceVersion.source_version_id`` and replays
its recorded resources as an inline ``ProviderStartResult``. No network IO, no
external dependency. The scheduler routes ``execution_mode == SHADOW`` source
versions through this provider so a new jurisdiction can be exercised end-to-end
without touching the upstream server.

Cassette format (``{cassette_dir}/{source_version_id}.json``)::

    {
        "provider_name": "firecrawl",
        "inline_resources": [
            {
                "source_url": "https://example.com/decisions/1",
                "final_url": "https://example.com/decisions/1",
                "content_type": "text/html",
                "body": "...markdown...",
                "title": "Decision 1",
                "http_status": 200,
                "discovery_depth": 1,
                "metadata": {}
            }
        ]
    }
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from platform_control.errors import ProviderConfigurationError
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.services.acquisition_provider import (
    ProviderPlan,
    ProviderResource,
    ProviderStartResult,
)


class CassetteProvider:
    provider_name = "cassette"

    def __init__(self, cassette_dir: Path) -> None:
        self.cassette_dir = Path(cassette_dir)

    def _cassette_path(self, source_version: SourceVersion) -> Path:
        return self.cassette_dir / f"{source_version.source_version_id}.json"

    def _load_cassette(self, source_version: SourceVersion) -> dict[str, Any]:
        path = self._cassette_path(source_version)
        if not path.exists():
            raise ProviderConfigurationError(
                f"Cassette not found for source_version {source_version.source_version_id} "
                f"at {path}. Record one with 'pc fetch --record' or place a fixture there."
            )
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    async def start_run(
        self,
        source: Source,
        source_version: SourceVersion,
        run: Run,
    ) -> ProviderStartResult:
        del source
        cassette = self._load_cassette(source_version)
        raw_resources = cassette.get("inline_resources") or []
        if not isinstance(raw_resources, list):
            raise ProviderConfigurationError(
                f"Cassette {self._cassette_path(source_version)} inline_resources must be a list."
            )

        resources: list[ProviderResource] = []
        for entry in raw_resources:
            if not isinstance(entry, dict):
                raise ProviderConfigurationError(
                    f"Cassette {self._cassette_path(source_version)} contains a non-object entry."
                )
            resources.append(
                ProviderResource(
                    source_url=str(entry.get("source_url") or ""),
                    final_url=str(entry.get("final_url") or entry.get("source_url") or ""),
                    content_type=str(entry.get("content_type") or "text/html"),
                    body=str(entry.get("body") or ""),
                    title=entry.get("title"),
                    http_status=entry.get("http_status"),
                    discovery_depth=entry.get("discovery_depth"),
                    metadata=dict(entry.get("metadata") or {"provider": self.provider_name}),
                )
            )

        return ProviderStartResult(
            provider=str(cassette.get("provider_name") or self.provider_name),
            external_job_id=f"cassette_{run.run_id}",
            request_payload={
                "cassette_path": str(self._cassette_path(source_version)),
                "resource_count": len(resources),
            },
            response_payload={
                "provider": self.provider_name,
                "captured": len(resources),
            },
            inline_resources=resources,
            inline_failure_reason=(
                None if resources else "Cassette contained no inline_resources."
            ),
        )

    def plan(
        self,
        source: Source,
        source_version: SourceVersion,
    ) -> ProviderPlan:
        del source
        path = self._cassette_path(source_version)
        notes = [f"cassette_path={path}"]
        if not path.exists():
            notes.append("cassette_missing=true")
            return ProviderPlan(
                provider=self.provider_name,
                mode="shadow",
                notes=notes,
            )
        cassette = self._load_cassette(source_version)
        resource_count = len(cassette.get("inline_resources") or [])
        return ProviderPlan(
            provider=self.provider_name,
            mode="shadow",
            estimated_request_count=resource_count,
            notes=notes,
            raw={"cassette_provider_name": cassette.get("provider_name")},
        )
