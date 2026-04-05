from __future__ import annotations

from typing import Any

import httpx

from platform_control.config import Settings
from platform_control.domain import AcquisitionProvider, FirecrawlMode, RunMode
from platform_control.errors import ProviderConfigurationError
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.services.acquisition_provider import ProviderStartResult


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
