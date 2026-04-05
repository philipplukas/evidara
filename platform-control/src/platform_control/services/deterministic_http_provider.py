from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx

from platform_control.errors import ProviderConfigurationError
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.services.acquisition_provider import (
    ProviderResource,
    ProviderStartResult,
)


class DeterministicHttpProvider:
    provider_name = "deterministic_http"

    async def start_run(
        self,
        source: Source,
        source_version: SourceVersion,
        run: Run,
    ) -> ProviderStartResult:
        del source
        acquisition_spec = source_version.acquisition_spec or {}
        seed_urls = self._seed_urls(acquisition_spec)
        timeout_seconds = float(acquisition_spec.get("request_timeout_seconds") or 30.0)
        user_agent = str(
            acquisition_spec.get("user_agent")
            or "platform-control-deterministic-http/1.0 (+https://evidara.ai)"
        )
        max_content_bytes = int(acquisition_spec.get("max_content_bytes") or 2_000_000)

        resources: list[ProviderResource] = []
        failures: list[dict[str, str]] = []

        headers = {"User-Agent": user_agent}
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
            for url in seed_urls:
                try:
                    response = await client.get(url, headers=headers)
                    body = response.text
                    if len(body.encode("utf-8")) > max_content_bytes:
                        failures.append(
                            {
                                "url": url,
                                "error": f"response exceeded max_content_bytes={max_content_bytes}",
                            }
                        )
                        continue
                    content_type = response.headers.get("content-type", "text/html")
                    normalized_content_type = content_type.split(";")[0].strip().lower()
                    if normalized_content_type == "application/text":
                        normalized_content_type = "text/plain"
                    resources.append(
                        ProviderResource(
                            source_url=url,
                            final_url=str(response.url),
                            content_type=normalized_content_type,
                            body=body,
                            title=_title_from_html(body),
                            http_status=response.status_code,
                            discovery_depth=0,
                            metadata={
                                "provider": self.provider_name,
                                "requested_url": url,
                                "fetched_at": datetime.now(UTC).isoformat(),
                            },
                        )
                    )
                except Exception as exc:  # pragma: no cover - defensive capture path
                    failures.append({"url": url, "error": str(exc)})

        response_payload = {
            "provider": self.provider_name,
            "requested": len(seed_urls),
            "captured": len(resources),
            "failed": len(failures),
            "failures": failures,
        }
        inline_failure_reason = None
        if not resources:
            inline_failure_reason = "Deterministic HTTP provider did not capture any resources."

        return ProviderStartResult(
            provider=self.provider_name,
            external_job_id=f"dethttp_{run.run_id}",
            request_payload={
                "seed_urls": seed_urls,
                "timeout_seconds": timeout_seconds,
                "max_content_bytes": max_content_bytes,
            },
            response_payload=response_payload,
            inline_resources=resources,
            inline_failure_reason=inline_failure_reason,
        )

    @staticmethod
    def _seed_urls(acquisition_spec: dict) -> list[str]:
        seed_urls = [
            str(url)
            for url in acquisition_spec.get("seed_urls", [])
            if isinstance(url, str) and url.strip()
        ]
        seed_url = acquisition_spec.get("seed_url")
        if isinstance(seed_url, str) and seed_url.strip():
            seed_urls.append(seed_url)
        unique_urls: list[str] = []
        seen: set[str] = set()
        for url in seed_urls:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                continue
            if url in seen:
                continue
            unique_urls.append(url)
            seen.add(url)
        if not unique_urls:
            raise ProviderConfigurationError(
                "deterministic_http provider requires acquisition_spec.seed_url or seed_urls."
            )
        return unique_urls


def _title_from_html(body: str) -> str | None:
    marker_start = body.lower().find("<title>")
    marker_end = body.lower().find("</title>")
    if marker_start == -1 or marker_end == -1 or marker_end <= marker_start:
        return None
    return body[marker_start + len("<title>") : marker_end].strip() or None
