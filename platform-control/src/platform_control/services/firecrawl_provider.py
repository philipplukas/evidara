from __future__ import annotations

from typing import Any

import httpx

from platform_control.config import Settings
from platform_control.domain import AcquisitionProvider, FirecrawlMode, RunMode
from platform_control.errors import ProviderConfigurationError
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.services.acquisition_provider import ProviderPlan, ProviderStartResult


class FirecrawlProvider:
    provider_name = "firecrawl"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def start_run(
        self,
        source: Source,
        source_version: SourceVersion,
        run: Run,
    ) -> ProviderStartResult:
        if not self.settings.firecrawl_api_key:
            raise ProviderConfigurationError(
                "Firecrawl API key is required before starting acquisition runs."
            )

        payload, endpoint = self._build_request_payload(source, source_version, run)
        headers = {"Authorization": f"Bearer {self.settings.firecrawl_api_key}"}

        async with httpx.AsyncClient(
            base_url=self.settings.firecrawl_base_url,
            timeout=30.0,
        ) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            response_payload = response.json()

        external_job_id = str(response_payload.get("id", ""))
        if not external_job_id:
            raise ProviderConfigurationError("Firecrawl response did not include a job ID.")

        return ProviderStartResult(
            provider=self.provider_name,
            external_job_id=external_job_id,
            request_payload=payload,
            response_payload=response_payload,
        )

    def plan(
        self,
        source: Source,
        source_version: SourceVersion,
    ) -> ProviderPlan:
        del source
        acquisition_spec = source_version.acquisition_spec or {}
        mode_value = str(acquisition_spec.get("mode") or FirecrawlMode.CRAWL.value)
        mode = FirecrawlMode(mode_value)
        seed_urls: list[str]
        estimated_request_count: int | None
        if mode is FirecrawlMode.CRAWL:
            seed_url = acquisition_spec.get("seed_url")
            seed_urls = [str(seed_url)] if seed_url else []
            estimated_request_count = int(acquisition_spec.get("limit", 20))
        else:
            seed_urls = [str(url) for url in acquisition_spec.get("seed_urls") or []]
            estimated_request_count = len(seed_urls) or None
        notes: list[str] = []
        if acquisition_spec.get("zero_data_retention"):
            notes.append("zero_data_retention=true")
        return ProviderPlan(
            provider=self.provider_name,
            mode=mode.value,
            seed_urls=seed_urls,
            estimated_request_count=estimated_request_count,
            max_discovery_depth=(
                int(acquisition_spec.get("max_discovery_depth", 2))
                if mode is FirecrawlMode.CRAWL
                else None
            ),
            include_paths=list(acquisition_spec.get("include_paths") or []),
            exclude_paths=list(acquisition_spec.get("exclude_paths") or []),
            user_agent=acquisition_spec.get("user_agent"),
            request_timeout_seconds=acquisition_spec.get("request_timeout_seconds"),
            notes=notes,
            raw=dict(acquisition_spec),
        )

    def _build_request_payload(
        self,
        source: Source,
        source_version: SourceVersion,
        run: Run,
    ) -> tuple[dict[str, Any], str]:
        acquisition_spec = source_version.acquisition_spec
        provider_name = str(acquisition_spec.get("provider") or AcquisitionProvider.FIRECRAWL.value)
        if provider_name != "firecrawl":
            raise ProviderConfigurationError(
                "Firecrawl provider cannot dispatch non-firecrawl acquisition specs."
            )
        mode = FirecrawlMode(acquisition_spec["mode"])

        webhook_config: dict[str, Any] | None = None
        if self.settings.firecrawl_webhook_url:
            events = ["crawl.started", "crawl.page", "crawl.completed", "crawl.failed"]
            webhook_config = {
                "url": self.settings.firecrawl_webhook_url,
                "metadata": {
                    "run_id": run.run_id,
                    "source_id": source.source_id,
                    "source_version_id": source_version.source_version_id,
                    "mode": run.mode.value,
                    "run_scope_kind": run.scope.get("kind"),
                    "replay_mode": (run.replay or {}).get("mode"),
                },
                "events": events,
            }

        formats = acquisition_spec.get("scrape_formats", ["markdown", "html"])
        if mode is FirecrawlMode.CRAWL:
            seed_url = acquisition_spec.get("seed_url")
            if not seed_url:
                raise ProviderConfigurationError(
                    "Firecrawl crawl mode requires acquisition_spec.seed_url."
                )

            payload: dict[str, Any] = {
                "url": seed_url,
                "limit": acquisition_spec.get("limit", 20),
                "maxDiscoveryDepth": acquisition_spec.get("max_discovery_depth", 2),
                "scrapeOptions": {"formats": formats},
                "zeroDataRetention": acquisition_spec.get("zero_data_retention", False),
                "metadata": {
                    "run_id": run.run_id,
                    "source_id": source.source_id,
                    "source_version_id": source_version.source_version_id,
                    "run_mode": RunMode(run.mode).value,
                    "run_scope": run.scope,
                    "replay": run.replay,
                },
            }
            if acquisition_spec.get("include_paths"):
                payload["includePaths"] = acquisition_spec["include_paths"]
            if acquisition_spec.get("exclude_paths"):
                payload["excludePaths"] = acquisition_spec["exclude_paths"]
            if webhook_config:
                payload["webhook"] = webhook_config
            return payload, "crawl"

        seed_urls = acquisition_spec.get("seed_urls") or []
        if not seed_urls:
            raise ProviderConfigurationError(
                "Firecrawl batch_scrape mode requires acquisition_spec.seed_urls."
            )

        payload = {
            "urls": seed_urls,
            "formats": formats,
            "zeroDataRetention": acquisition_spec.get("zero_data_retention", False),
        }
        if webhook_config:
            payload["webhook"] = webhook_config
        return payload, "batch/scrape"
