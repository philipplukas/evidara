from __future__ import annotations

import ipaddress
import socket
from datetime import UTC, datetime
from urllib.parse import urljoin, urlparse

import httpx

from platform_control.errors import ProviderConfigurationError
from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.services.acquisition_provider import (
    AcquisitionReadiness,
    ProviderPlan,
    ProviderResource,
    ProviderStartResult,
)
from platform_control.services.politeness import HostRateLimiter, limited_get

IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


class DeterministicHttpProvider:
    provider_name = "deterministic_http"
    readiness = AcquisitionReadiness.LIVE
    _MAX_REDIRECTS = 5

    def __init__(self, rate_limiter: HostRateLimiter | None = None) -> None:
        self.rate_limiter = rate_limiter

    _DENYLIST_HOSTNAMES = {
        "localhost",
        "metadata",
        "metadata.google.internal",
        "metadata.google.internal.",
    }
    _DENYLIST_NETWORKS = (
        ipaddress.ip_network("0.0.0.0/8"),
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("100.64.0.0/10"),
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("169.254.0.0/16"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.0.0.0/24"),
        ipaddress.ip_network("192.0.2.0/24"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("198.18.0.0/15"),
        ipaddress.ip_network("198.51.100.0/24"),
        ipaddress.ip_network("203.0.113.0/24"),
        ipaddress.ip_network("224.0.0.0/4"),
        ipaddress.ip_network("240.0.0.0/4"),
        ipaddress.ip_network("::/128"),
        ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("fe80::/10"),
        ipaddress.ip_network("fc00::/7"),
        ipaddress.ip_network("ff00::/8"),
    )

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
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False) as client:
            for url in seed_urls:
                try:
                    resolved_url, response = await self._request_with_safe_redirects(
                        client=client,
                        url=url,
                        headers=headers,
                    )
                    if not response.is_success:
                        failures.append(
                            {
                                "url": url,
                                "error": f"received non-success status {response.status_code}",
                            }
                        )
                        continue

                    body_bytes = await self._read_body_limited(
                        response=response,
                        max_content_bytes=max_content_bytes,
                    )
                    if body_bytes is None:
                        failures.append(
                            {
                                "url": url,
                                "error": f"response exceeded max_content_bytes={max_content_bytes}",
                            }
                        )
                        continue

                    charset = response.charset_encoding or "utf-8"
                    body = body_bytes.decode(charset, errors="replace")
                    content_type = response.headers.get("content-type", "text/html")
                    normalized_content_type = content_type.split(";")[0].strip().lower()
                    if normalized_content_type == "application/text":
                        normalized_content_type = "text/plain"
                    resources.append(
                        ProviderResource(
                            source_url=url,
                            final_url=resolved_url,
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

    def plan(
        self,
        source: Source,
        source_version: SourceVersion,
    ) -> ProviderPlan:
        del source
        acquisition_spec = source_version.acquisition_spec or {}
        seed_urls = self._seed_urls(acquisition_spec)
        return ProviderPlan(
            provider=self.provider_name,
            seed_urls=seed_urls,
            estimated_request_count=len(seed_urls),
            user_agent=str(
                acquisition_spec.get("user_agent")
                or "platform-control-deterministic-http/1.0 (+https://evidara.ai)"
            ),
            request_timeout_seconds=float(acquisition_spec.get("request_timeout_seconds") or 30.0),
            raw=dict(acquisition_spec),
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

    async def _request_with_safe_redirects(
        self,
        *,
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
    ) -> tuple[str, httpx.Response]:
        current_url = self._validate_target_url(url)
        for _ in range(self._MAX_REDIRECTS + 1):
            response = await self._get_with_rate_limit(
                client=client, url=current_url, headers=headers
            )
            if not response.is_redirect:
                return current_url, response
            location = response.headers.get("location")
            if not location:
                return current_url, response
            next_url = urljoin(current_url, location)
            current_url = self._validate_target_url(next_url)
        raise ProviderConfigurationError(
            f"deterministic_http provider exceeded max redirects ({self._MAX_REDIRECTS}) for {url}."
        )

    async def _get_with_rate_limit(
        self,
        *,
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
    ) -> httpx.Response:
        return await limited_get(client, url, limiter=self.rate_limiter, headers=headers)

    async def _read_body_limited(
        self,
        *,
        response: httpx.Response,
        max_content_bytes: int,
    ) -> bytes | None:
        collected = bytearray()
        async for chunk in response.aiter_bytes():
            collected.extend(chunk)
            if len(collected) > max_content_bytes:
                return None
        return bytes(collected)

    def _validate_target_url(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ProviderConfigurationError(
                f"deterministic_http provider only supports http/https URLs: {url}"
            )
        hostname = (parsed.hostname or "").strip().lower().rstrip(".")
        if not hostname:
            raise ProviderConfigurationError(f"deterministic_http provider requires host: {url}")
        if hostname in self._DENYLIST_HOSTNAMES:
            raise ProviderConfigurationError(
                f"deterministic_http provider blocked restricted host '{hostname}'."
            )
        for ip in self._resolve_ips(hostname):
            if self._is_restricted_ip(ip):
                raise ProviderConfigurationError(
                    "deterministic_http provider blocked restricted address "
                    f"'{ip}' for host '{hostname}'."
                )
        return url

    @staticmethod
    def _resolve_ips(hostname: str) -> set[IpAddress]:
        resolved: set[IpAddress] = set()
        try:
            addrinfos = socket.getaddrinfo(hostname, None)
        except socket.gaierror as exc:
            raise ProviderConfigurationError(
                f"deterministic_http provider could not resolve host '{hostname}'."
            ) from exc
        for info in addrinfos:
            sockaddr = info[4]
            if not sockaddr:
                continue
            ip_text = str(sockaddr[0])
            resolved.add(ipaddress.ip_address(ip_text))
        return resolved

    def _is_restricted_ip(self, ip: IpAddress) -> bool:
        return any(ip in network for network in self._DENYLIST_NETWORKS)


def _title_from_html(body: str) -> str | None:
    marker_start = body.lower().find("<title>")
    marker_end = body.lower().find("</title>")
    if marker_start == -1 or marker_end == -1 or marker_end <= marker_start:
        return None
    return body[marker_start + len("<title>") : marker_end].strip() or None
