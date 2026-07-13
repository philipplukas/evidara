"""Swiss federal court decisions provider (BGer / BVGer / BStGer / BPGer).

Fetches published Swiss *federal* court rulings as HTML and shapes them into
canonical :class:`ProviderResource` objects carrying case-law citation
metadata (docket number, BGE reference, ECLI, court, decision date).

Two acquisition inputs are supported, mirroring the shape of
``ris_ogd_provider`` (listing → refs → fetch each) but over plain HTML:

- ``seed_urls`` / ``seed_url`` — direct decision-document URLs to fetch.
- ``index_urls`` — listing/search pages to *discover* decision links from
  (one level deep), matched against ``link_pattern`` and the host allow-list.

Both are optional; supplying either is enough. Every fetched URL is checked
against a pinned host allow-list (the official court portals plus the open
aggregator ``entscheidsuche.ch``) before any request is made, so a
mis-configured seed cannot make the provider fetch an arbitrary host.

Scaffold status
---------------
``live_ready = False``: the fetch/parse logic is implemented and unit-tested
against captured fixtures, but no live source has been accepted from a running
environment yet. The loader's two-key lock (``provider.live_ready`` +
``template.enabled``) keeps blueprint templates referencing this provider from
firing until an operator captures acceptance-run evidence via
``scripts/ch-bger-fast-loop.sh`` and flips both keys. See issue #530.

Compliance
----------
Swiss federal court decisions carry no explicit open-data licence, so they
belong in the public-official tier (``cp_ch_court_decisions``: robots=strict,
~20 rpm, 2 concurrent, 365-day retention) rather than the Fedlex open-data
tier. Because compliance policy is resolved per *jurisdiction* today and
``jur_ch_federal`` binds the Fedlex open-data policy (correctly, for
legislation), binding the court policy to court runs is a live-enablement
follow-up: the ``Authority`` model already carries a ``compliance_policy_id``
FK, so authority-level resolution is the intended seam. The provider still
routes every request through :func:`limited_get`, so whatever limiter the run
resolves is honoured.
"""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from platform_control.models.run import Run
from platform_control.models.source import Source
from platform_control.models.source_version import SourceVersion
from platform_control.services.acquisition_provider import (
    ProviderPlan,
    ProviderResource,
    ProviderStartResult,
)
from platform_control.services.politeness import limited_get

_USER_AGENT = "evidara-ch-court-decisions/1.0 (+https://evidara.ai)"

# Registrable domains of the Swiss federal courts plus the open aggregator.
# Subdomains (e.g. ``www.bger.ch``) are matched by suffix in ``_host_allowed``.
_DEFAULT_ALLOWED_HOSTS: tuple[str, ...] = (
    "bger.ch",
    "bvger.ch",
    "bstger.ch",
    "bpger.ch",
    "entscheidsuche.ch",
)

# Swiss federal-court file numbers. Two shapes are recognised:
#   * BGer/BStGer/BPGer:  ``1C_123/2024``, ``6B_45/2023`` (chamber code + ``_``)
#   * BVGer:              ``A-1234/2024``, ``B-567/2023``  (division letter A–F + ``-``)
# Both are language-neutral, so the same regex serves DE/FR/IT rulings.
_DOCKET_RE = re.compile(r"\b(?:\d{1,2}[A-Z]?_\d+|[A-F]-\d+)/\d{4}\b")
# Official reporter citation, e.g. ``BGE 149 III 1`` / ``ATF 149 III 1`` / ``DTF 149 III 1``.
_BGE_RE = re.compile(r"\b(?:BGE|ATF|DTF)\s+\d{1,3}\s+[IVX]+\s+\d+\b")
# European Case Law Identifier, e.g. ``ECLI:CH:BGER:2024:...`` / ``ECLI:CH:BVGER:2024:...``.
_ECLI_RE = re.compile(r"ECLI:CH:[A-Z0-9]+:\d{4}:[A-Za-z0-9._-]+")
# Long-form decision date in any of the three official languages, e.g.
# ``12. März 2024`` (DE), ``12 mars 2024`` / ``1er mars 2024`` (FR),
# ``12 marzo 2024`` (IT). The day separator (``.``) and the ``er`` ordinal are
# both optional so the single pattern spans all three forms.
_MONTH_NAMES = (
    # German
    "Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember|"
    # French
    "janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre|"
    # Italian
    "gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre"
)
_DATE_RE = re.compile(
    r"\b\d{1,2}(?:er)?\.?\s?(?:" + _MONTH_NAMES + r")\s?\d{4}\b",
    re.IGNORECASE,
)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
# First-heading fallback when a decision page ships an empty/boilerplate title.
_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_HREF_RE = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
# Discovery default: decision links carry a docket in the URL or end in .html.
_DEFAULT_LINK_PATTERN = r"\d{1,2}[A-Z]?_\d+/\d{4}|[A-F]-\d+/\d{4}|\.html?($|[?#])"

_DEFAULT_MAX_DOCUMENTS = 50
_DEFAULT_MAX_CONTENT_BYTES = 5_000_000
_DEFAULT_TIMEOUT_SECONDS = 30.0

_COURT_BY_HOST: dict[str, str] = {
    "bger.ch": "bger",
    "bvger.ch": "bvger",
    "bstger.ch": "bstger",
    "bpger.ch": "bpger",
}


def _registrable_host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _host_allowed(url: str, allowed: tuple[str, ...]) -> bool:
    host = _registrable_host(url)
    if not host:
        return False
    return any(
        host == allowed_host or host.endswith("." + allowed_host) for allowed_host in allowed
    )


def _court_from_url(url: str, hint: str | None) -> str | None:
    if hint:
        return hint
    host = _registrable_host(url)
    for allowed_host, court in _COURT_BY_HOST.items():
        if host == allowed_host or host.endswith("." + allowed_host):
            return court
    return None


def _seed_list(acquisition_spec: dict[str, Any], key: str) -> list[str]:
    raw = acquisition_spec.get(key)
    if raw is None and key == "seed_urls":
        raw = acquisition_spec.get("seed_url")
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(item) for item in raw if isinstance(item, str) and item.strip()]
    return []


def _clean_inline_text(raw: str) -> str:
    """Strip nested tags/entities and collapse whitespace to a single line."""
    without_tags = _TAG_RE.sub(" ", raw)
    unescaped = html.unescape(without_tags)
    return re.sub(r"\s+", " ", unescaped).strip()


def _extract_title(body_text: str) -> str | None:
    """Title from ``<title>``; fall back to the first ``<h1>`` when it is empty.

    Many court pages ship a boilerplate or blank ``<title>`` (e.g. just the
    portal name) while the actual case caption lives in an ``<h1>``. Falling
    back keeps a meaningful title instead of dropping to the URL basename.
    """
    match = _TITLE_RE.search(body_text)
    if match:
        title = _clean_inline_text(match.group(1))
        if title:
            return title
    h1_match = _H1_RE.search(body_text)
    if h1_match:
        heading = _clean_inline_text(h1_match.group(1))
        if heading:
            return heading
    return None


def _extract_links(
    base_url: str,
    body_text: str,
    pattern: re.Pattern[str],
    allowed: tuple[str, ...],
) -> list[str]:
    """Return decision links found on an index page, absolute + host-checked."""
    seen: set[str] = set()
    links: list[str] = []
    for match in _HREF_RE.finditer(body_text):
        # Unescape HTML entities (e.g. ``&amp;`` in query strings) so the
        # discovered URL is the real target, not a broken entity-laden one.
        href = html.unescape(match.group(1).strip())
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        absolute = urljoin(base_url, href)
        if absolute in seen:
            continue
        if not _host_allowed(absolute, allowed):
            continue
        if not pattern.search(absolute):
            continue
        seen.add(absolute)
        links.append(absolute)
    return links


def _extract_citation_metadata(body_text: str) -> dict[str, str | None]:
    docket = _DOCKET_RE.search(body_text)
    bge = _BGE_RE.search(body_text)
    ecli = _ECLI_RE.search(body_text)
    date = _DATE_RE.search(body_text)
    return {
        "docket": docket.group(0) if docket else None,
        "bge_reference": bge.group(0) if bge else None,
        "ecli": ecli.group(0) if ecli else None,
        "decision_date": date.group(0) if date else None,
    }


class ChCourtDecisionsProvider:
    """Acquisition provider for Swiss federal court decisions (HTML)."""

    provider_name = "ch_court_decisions"
    live_ready = False

    async def start_run(
        self,
        source: Source,
        source_version: SourceVersion,
        run: Run,
    ) -> ProviderStartResult:
        del source
        acquisition_spec = source_version.acquisition_spec or {}
        allowed_hosts = self._allowed_hosts(acquisition_spec)
        court_hint = acquisition_spec.get("court")
        max_documents = int(acquisition_spec.get("max_documents") or _DEFAULT_MAX_DOCUMENTS)
        max_content_bytes = int(
            acquisition_spec.get("max_content_bytes") or _DEFAULT_MAX_CONTENT_BYTES
        )
        timeout_seconds = float(
            acquisition_spec.get("request_timeout_seconds") or _DEFAULT_TIMEOUT_SECONDS
        )
        user_agent = str(acquisition_spec.get("user_agent") or _USER_AGENT)
        link_pattern = re.compile(
            str(acquisition_spec.get("link_pattern") or _DEFAULT_LINK_PATTERN)
        )

        seed_urls = _seed_list(acquisition_spec, "seed_urls")
        index_urls = _seed_list(acquisition_spec, "index_urls")

        resources: list[ProviderResource] = []
        failures: list[dict[str, str]] = []
        seen_targets: set[str] = set()
        skipped_disallowed = 0
        discovered = 0

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout=timeout_seconds, connect=min(10.0, timeout_seconds)),
            headers={"User-Agent": user_agent},
            follow_redirects=True,
        ) as client:
            # Discovery pass: expand index/listing pages into decision links.
            targets: list[tuple[str, str]] = []
            for url in seed_urls:
                if not _host_allowed(url, allowed_hosts):
                    skipped_disallowed += 1
                    failures.append({"url": url, "error": "seed URL host not in allow-list"})
                    continue
                if url not in seen_targets:
                    seen_targets.add(url)
                    targets.append((url, "seed"))

            for index_url in index_urls:
                if not _host_allowed(index_url, allowed_hosts):
                    skipped_disallowed += 1
                    failures.append({"url": index_url, "error": "index URL host not in allow-list"})
                    continue
                try:
                    listing = await limited_get(client, index_url)
                    listing.raise_for_status()
                except httpx.TimeoutException:
                    failures.append(
                        {"url": index_url, "error": f"index timed out after {timeout_seconds:.1f}s"}
                    )
                    continue
                except Exception as exc:  # noqa: BLE001 - capture and continue
                    failures.append({"url": index_url, "error": f"index fetch: {exc}"})
                    continue
                charset = listing.charset_encoding or "utf-8"
                listing_body = listing.content.decode(charset, errors="replace")
                for link in _extract_links(
                    str(listing.url), listing_body, link_pattern, allowed_hosts
                ):
                    if link in seen_targets:
                        continue
                    seen_targets.add(link)
                    discovered += 1
                    targets.append((link, "index"))

            # Fetch pass: cap at max_documents, fetch each decision document.
            for url, discovery_source in targets[:max_documents]:
                doc = await self._fetch_decision(
                    client=client,
                    url=url,
                    discovery_source=discovery_source,
                    court_hint=court_hint,
                    max_content_bytes=max_content_bytes,
                    timeout_seconds=timeout_seconds,
                    run=run,
                )
                if isinstance(doc, ProviderResource):
                    resources.append(doc)
                else:
                    failures.append(doc)

        response_payload = {
            "provider": self.provider_name,
            "seed_urls": len(seed_urls),
            "index_urls": len(index_urls),
            "discovered": discovered,
            "captured": len(resources),
            "failed": len(failures),
            "skipped_disallowed": skipped_disallowed,
            "failures": failures[:20],
        }
        inline_failure_reason = None
        if not resources:
            inline_failure_reason = (
                f"CH court decisions provider did not capture any resources "
                f"(failures={len(failures)})."
            )

        return ProviderStartResult(
            provider=self.provider_name,
            external_job_id=f"ch_court_decisions_{run.run_id}",
            request_payload={
                "seed_urls": seed_urls,
                "index_urls": index_urls,
                "court": court_hint,
                "max_documents": max_documents,
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
        seed_urls = _seed_list(acquisition_spec, "seed_urls")
        index_urls = _seed_list(acquisition_spec, "index_urls")
        max_documents = int(acquisition_spec.get("max_documents") or _DEFAULT_MAX_DOCUMENTS)
        notes: list[str] = []
        if court := acquisition_spec.get("court"):
            notes.append(f"court={court}")
        if index_urls:
            notes.append(f"discovery from {len(index_urls)} index url(s)")
        return ProviderPlan(
            provider=self.provider_name,
            mode="html_court_decisions",
            seed_urls=[*seed_urls, *index_urls],
            estimated_request_count=len(index_urls) + max_documents,
            user_agent=str(acquisition_spec.get("user_agent") or _USER_AGENT),
            request_timeout_seconds=float(
                acquisition_spec.get("request_timeout_seconds") or _DEFAULT_TIMEOUT_SECONDS
            ),
            notes=notes,
            raw=dict(acquisition_spec),
        )

    @staticmethod
    def _allowed_hosts(acquisition_spec: dict[str, Any]) -> tuple[str, ...]:
        override = acquisition_spec.get("allowed_hosts")
        if isinstance(override, list):
            hosts = tuple(
                str(h).strip().lower() for h in override if isinstance(h, str) and h.strip()
            )
            if hosts:
                return hosts
        return _DEFAULT_ALLOWED_HOSTS

    async def _fetch_decision(
        self,
        *,
        client: httpx.AsyncClient,
        url: str,
        discovery_source: str,
        court_hint: str | None,
        max_content_bytes: int,
        timeout_seconds: float,
        run: Run,
    ) -> ProviderResource | dict[str, str]:
        try:
            response = await limited_get(client, url)
            response.raise_for_status()
        except httpx.TimeoutException:
            return {"url": url, "error": f"timed out after {timeout_seconds:.1f}s"}
        except Exception as exc:  # noqa: BLE001 - capture and continue
            return {"url": url, "error": str(exc)}

        body_bytes = response.content
        if len(body_bytes) > max_content_bytes:
            return {"url": url, "error": f"content exceeds {max_content_bytes} bytes"}

        charset = response.charset_encoding or "utf-8"
        body = body_bytes.decode(charset, errors="replace")
        normalized_ct = (
            response.headers.get("content-type", "text/html").split(";")[0].strip().lower()
        )
        final_url = str(response.url)
        citation = _extract_citation_metadata(body)

        return ProviderResource(
            source_url=url,
            final_url=final_url,
            content_type=normalized_ct,
            body=body,
            title=(
                _extract_title(body)
                or citation.get("docket")
                or citation.get("ecli")
                or url.rsplit("/", 1)[-1]
            ),
            http_status=response.status_code,
            discovery_depth=1 if discovery_source == "index" else 0,
            metadata={
                "provider": self.provider_name,
                "court": _court_from_url(final_url, court_hint),
                "document_type": "decision",
                "discovery_source": discovery_source,
                "docket": citation.get("docket"),
                "bge_reference": citation.get("bge_reference"),
                "ecli": citation.get("ecli"),
                "decision_date": citation.get("decision_date"),
                "fetched_at": datetime.now(UTC).isoformat(),
                "run_id": run.run_id,
            },
        )
