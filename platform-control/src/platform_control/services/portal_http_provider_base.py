"""Shared base for jurisdiction-scoped portal HTTP providers.

German Länder (`gesetze-bayern.de`, `recht.nrw.de`, `landesrecht-bw.de`,
…) and Italian regioni (`normelombardia.consiglio.regione.lombardia.it`,
…) each publish legal content on their own HTML portal. The portals
differ in URL shape and markup but share the same acquisition flow:

  1. Start from one or more seed URLs declared in the blueprint
     template (e.g. a statute landing page).
  2. Fetch each URL with deterministic HTTP, honouring the same safety
     limits as DeterministicHttpProvider (max content bytes, timeout,
     host allow-list).
  3. Pull the title from `<title>` (or a configured selector) and
     return the raw HTML as `ProviderResource.body`. Document-
     intelligence handles the structural parsing downstream.

`PortalHttpProviderBase` captures that shared logic. Subclasses
(`BundeslandHttpProvider`, `RegioneHttpProvider`) declare:

- `provider_name`: the enum value the blueprint references.
- `subdivision_spec_key`: the `acquisition_spec.<key>` name
  (`"bundesland"` vs. `"regione"`).
- `subdivision_country`: ISO 3166-1 alpha-2 of the country scope (`"DE"`
  vs. `"IT"`). Used to validate the ISO 3166-2 code against
  `contracts/vocabularies/subdivisions.json`.
- `supported_portals`: ISO 3166-2 code → portal host (for allow-list
  gating and logging).

Subclasses are free to stay thin; per-portal nuance (custom auth,
JavaScript rendering) is a future concern and would warrant a dedicated
provider for that portal.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, ClassVar
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

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


class PortalHttpProviderBase:
    """Template-method base for DE Bundesland / IT regione HTTP providers."""

    provider_name: ClassVar[str]
    subdivision_spec_key: ClassVar[str]
    subdivision_country: ClassVar[str]
    supported_portals: ClassVar[dict[str, str]]
    live_ready: ClassVar[bool] = False

    async def start_run(
        self,
        source: Source,
        source_version: SourceVersion,
        run: Run,
    ) -> ProviderStartResult:
        del source
        acquisition_spec: dict[str, Any] = source_version.acquisition_spec or {}
        code = self._require_subdivision_code(acquisition_spec)
        portal_host = self._portal_host(code)
        seed_urls = self._seed_urls(acquisition_spec, portal_host=portal_host)
        timeout_seconds = float(acquisition_spec.get("request_timeout_seconds") or 30.0)
        max_content_bytes = int(acquisition_spec.get("max_content_bytes") or 5_000_000)

        resources: list[ProviderResource] = []
        failures: list[dict[str, str]] = []

        async with httpx.AsyncClient(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": "evidara-portal-http/1.0"},
        ) as client:
            for url in seed_urls:
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                    body = self._read_limited(response, max_content_bytes)
                    if not body:
                        failures.append({"url": url, "error": "empty response body"})
                        continue
                    charset = response.charset_encoding or "utf-8"
                    body_text = body.decode(charset, errors="replace")
                    title = self._extract_title(body_text) or url.rsplit("/", 1)[-1]
                    content_type = (
                        response.headers.get("content-type", "text/html")
                        .split(";", 1)[0]
                        .strip()
                        .lower()
                    )
                    resources.append(
                        ProviderResource(
                            source_url=url,
                            final_url=str(response.url),
                            content_type=content_type,
                            body=body_text,
                            title=title,
                            http_status=response.status_code,
                            discovery_depth=0,
                            metadata={
                                "provider": self.provider_name,
                                self.subdivision_spec_key: code,
                                "subdivision": code,
                                "portal_host": portal_host,
                                "fetched_at": datetime.now(UTC).isoformat(),
                            },
                        )
                    )
                except Exception as exc:  # pragma: no cover - defensive capture
                    failures.append({"url": url, "error": str(exc)})

        response_payload = {
            "provider": self.provider_name,
            "requested": len(seed_urls),
            "captured": len(resources),
            "failed": len(failures),
            "failures": failures,
            self.subdivision_spec_key: code,
        }
        inline_failure_reason = None
        if not resources:
            inline_failure_reason = f"{self.provider_name} did not capture any resources for {code}"

        return ProviderStartResult(
            provider=self.provider_name,
            external_job_id=f"{self.provider_name}_{run.run_id}",
            request_payload={
                "seed_urls": seed_urls,
                self.subdivision_spec_key: code,
                "portal_host": portal_host,
            },
            response_payload=response_payload,
            inline_resources=resources,
            inline_failure_reason=inline_failure_reason,
        )

    # ─── Helpers ──────────────────────────────────────────────

    def _require_subdivision_code(self, acquisition_spec: dict[str, Any]) -> str:
        raw = acquisition_spec.get(self.subdivision_spec_key)
        if not isinstance(raw, str) or not raw.strip():
            raise ProviderConfigurationError(
                f"{self.provider_name} requires "
                f"acquisition_spec.{self.subdivision_spec_key} (ISO 3166-2 code)"
            )
        code = raw.strip().upper()
        if not code.startswith(f"{self.subdivision_country}-"):
            raise ProviderConfigurationError(
                f"{self.subdivision_spec_key} must be an ISO 3166-2:"
                f"{self.subdivision_country} code, got {raw!r}"
            )
        return code

    def _portal_host(self, code: str) -> str:
        host = self.supported_portals.get(code)
        if host is None:
            raise ProviderConfigurationError(
                f"{self.provider_name} has no supported portal for {code}. "
                f"Supported: {sorted(self.supported_portals)}"
            )
        return host

    def _seed_urls(
        self,
        acquisition_spec: dict[str, Any],
        *,
        portal_host: str,
    ) -> list[str]:
        raw = acquisition_spec.get("seed_urls") or acquisition_spec.get("seed_url")
        if isinstance(raw, str):
            candidates = [raw]
        elif isinstance(raw, list):
            candidates = [str(item) for item in raw if isinstance(item, str)]
        else:
            raise ProviderConfigurationError(
                f"{self.provider_name} requires acquisition_spec.seed_url or seed_urls"
            )
        if not candidates:
            raise ProviderConfigurationError(f"{self.provider_name} seed URL list is empty")
        validated: list[str] = []
        allowed_host = portal_host.split("/")[0]
        for url in candidates:
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"}:
                raise ProviderConfigurationError(
                    f"{self.provider_name} unsupported URL scheme: {url}"
                )
            if parsed.netloc != allowed_host and not parsed.netloc.endswith("." + allowed_host):
                raise ProviderConfigurationError(
                    f"{self.provider_name} seed URL host must match {allowed_host!r}, got: {url}"
                )
            validated.append(url)
        return validated

    @staticmethod
    def _extract_title(body_text: str) -> str | None:
        match = _TITLE_RE.search(body_text)
        if not match:
            return None
        title = match.group(1).strip()
        # Collapse whitespace; pages often contain newlines and tabs.
        title = re.sub(r"\s+", " ", title)
        return title or None

    @staticmethod
    def _read_limited(response: httpx.Response, max_bytes: int) -> bytes:
        body = response.content or b""
        if len(body) > max_bytes:
            body = body[:max_bytes]
        return body
