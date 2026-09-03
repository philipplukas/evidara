"""CH communal (Gemeinde) HTTP acquisition provider — LIVE (#584).

The ADR-0030 code key is open: acceptance evidence was captured against live
Zürich AS 554.510 on 2026-07-20 and is committed under
docs/runbooks/evidence/2026-07-20-ch-gemeinde-zuerich-acceptance.md (#735).

Swiss communal law is the layer the ADR-0033 acceptance test lives in
("Can the city ban a certain thing for dogs, year-round?"): the act being
challenged is a *communal* Hundereglement / Vollzugsvorschrift. 2,110
`jur_ch_gemeinde_*` jurisdictions are seeded, and before this module there
was no authority, no template and no provider for any of them — the
municipal layer was modelled and unreachable.

WHY THIS IS NOT A `canton_http` SUBCLASS
----------------------------------------
`PortalHttpProviderBase` keys its portal allow-list on ISO 3166-2 codes.
That standard stops at the canton: Swiss municipalities have no ISO code.
This provider therefore keys on the **BFS/OFS Gemeindenummer** — the same
federal statistical id the `jur_ch_gemeinde_<bfs>` seeds are generated
from, so `bfs_number` maps 1:1 onto a seeded jurisdiction (Zürich = 261).

WHAT THE CITY OF ZÜRICH ACTUALLY PUBLISHES (verified 2026-07-14)
----------------------------------------------------------------
The Amtliche Sammlung (AS) is a systematic collection whose URLs mirror
the AS number, e.g. AS 554.510 →
`/de/politik-und-verwaltung/politik-und-recht/amtliche-sammlung/5/554/510.html`.
That URL is a **metadata landing page**, not the law. It carries — in an
embedded JSON blob — the AS number, the title, Beschlussdatum,
Inkrafttreten, **Ausserkrafttreten** (the repeal date ADR-0033 notes the
corpus lacks), a version history, and a link to the operative text.

The operative text is a **PDF**. There is no HTML manifestation.

WHAT THIS PROVIDER NOW DOES (#584)
----------------------------------
It fetches the operative text and emits it as a `ProviderResource`, choosing
the modality from the manifestation's content type:

- PDF  -> `body_bytes` (raw). Decoding a PDF corrupts it, so it travels as
          bytes end-to-end (#590 / ADR-0037).
- HTML -> `body` (decoded), for communes that publish law as HTML.

Anything else is still recorded and skipped rather than guessed at. It never
emits the metadata landing page as a stand-in for the ordinance: indexing a
metadata stub as if it were the law is precisely the "demo that lies
convincingly" failure ADR-0033 exists to prevent.

Verified against live Zürich AS 554.510 ("Vollzugsvorschriften zum
Hundegesetz", in force 2017-09-01): the landing page parses and the linked
217 KB PDF is fetched intact.

WHY THE CODE KEY IS OPEN (`readiness = LIVE`)
---------------------------------------------
Both halves are built, and both are now evidenced against the live source:

- **Acquisition** (#584): the operative PDF is fetched and emitted as a binary
  `ProviderResource`, verified against live Zürich AS 554.510.
- **Normalisation** (#650, ADR-0041): the right-margin Randtitel splice that
  made the PDF path untrustworthy — "die Führung des **Organisation**
  Hundeverzeichnisses" — is fixed. `normalize/marginalia.py` partitions by
  shared line-start edges instead of x-projection gutters, and handles the
  recto-right / verso-left booklet layout the old left-only search could not.
  It is asserted against the **real** AS 554.510 PDF, not a synthetic one:
  document-intelligence/tests/test_marginalia.py.

The code key asserts both that the provider can physically acquire *and* that
the result is trustworthy. The second half was the real question — #650's splice
was found in this very document — so the acceptance run checked it: the ordinance
normalised into 9 sections with "die Führung des Hundeverzeichnisses" intact and
`Organisation` correctly separated as its Randtitel.

Templates still ship `enabled: false`. The config key is the operator's, flipped
from the admin panel with the evidence attached; this key only says the code
works. See #735.

HOW FAR THIS GENERALISES PAST ZÜRICH — read before quoting the next paragraph
-----------------------------------------------------------------------------
The BFS → host allow-list lives in `communal_portals.yaml`, so registering a
commune's *host* is a config edit, not a code change (#632).

The **parser is not** config. Everything above reads Stadt Zürich's Amtliche
Sammlung schema specifically: the `ASZ` field id, the `rechtstexte` link field,
`erlassdatum` / `inkrafttretendatum` / `ausserkrafttretendatum`, and a page title
of the form `<Erlass> | Stadt Zürich`. A commune whose portal has a different
page shape yields no manifestation link, and the run fails with the reason built
in `start_run` — correctly, but the remedy is a parser, not a config edit.

The earlier wording here ("adding a commune is a config change, not code") was
read as covering both halves, and sent #736 looking for a registration mechanism
when the binding constraint is per-portal parsing (see that issue's 2026-07-21
evidence comment). Landing one city is deliberate (#584) — communal law lives on
~2,000 independent sites and full coverage is a separate, much larger problem.
"""

from __future__ import annotations

import html as html_module
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import urljoin, urlparse

import httpx
import yaml

from platform_control.domain import AcquisitionProvider
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
from platform_control.services.politeness import limited_get

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
# The AS landing page renders its metadata into a web component whose
# `rows`/`columns` attributes hold an HTML-escaped JSON payload. We unescape
# once, then read the stable field ids out of it. Parsing the ids (rather than
# the surrounding markup) keeps this resilient to CMS template churn.
# Values embed escaped quotes (the `rechtstexte` field holds a whole <a> tag), so
# the capture must step over `\"` rather than stopping at the first quote.
_FIELD_RE_TEMPLATE = r'"id":"{field}","value":"((?:[^"\\]|\\.)*)"'
# The AS number appears as a row (`"id":"ASZ","value"`) and as a column header
# (`"key":"ASZ","text"`) depending on the page's table variant. Accept both.
_AS_NUMBER_RE = re.compile(r'"ASZ","(?:value|text)":"([0-9.]+)"')
# The operative-text link in the `rechtstexte` field. Zürich publishes PDFs, but
# the provider does not assume that: it reads the manifestation's extension and
# lets the carriability check below decide, so a commune that publishes HTML law
# acquires normally.
_MANIFESTATION_HREF_RE = re.compile(r'href=\\?"([^"\\]+\.(?:pdf|html?|xml))\\?"', re.IGNORECASE)
_CONTENT_TYPE_BY_SUFFIX: dict[str, str] = {
    "pdf": "application/pdf",
    "html": "text/html",
    "htm": "text/html",
    "xml": "application/xml",
}

# Text manifestations, carried as decoded `body`.
_TEXT_CONTENT_TYPES = frozenset(
    {"text/html", "application/xhtml+xml", "application/xml", "text/xml"}
)
# Binary manifestations, carried as raw `body_bytes` (#590/ADR-0037). Communal law
# is largely PDF-only, so this is the common case here rather than the exception.
_BINARY_CONTENT_TYPES = frozenset({"application/pdf"})
# Anything outside both sets is still recorded and skipped rather than guessed at.
_CARRIABLE_CONTENT_TYPES = _TEXT_CONTENT_TYPES | _BINARY_CONTENT_TYPES

# Shared so the per-URL failure and the run-level failure_reason cannot drift; the
# run-level message keys off this exact string to tell "unparseable page shape" apart
# from "seeds wrong / portal down" (#784).
_NO_MANIFESTATION_ERROR = "no operative-text manifestation found on landing page"

_SWISS_DATE_RE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})$")


@dataclass(frozen=True, slots=True)
class CommunalPortal:
    """A commune's legal-collection portal, keyed by BFS number.

    `canton_jurisdiction_id` is the commune's parent canton. Municipal
    documents must link up to it so the norm-hierarchy walk can ask which
    cantonal law delegates the competence being exercised (ADR-0033).
    """

    host: str
    canton_jurisdiction_id: str


_COMMUNAL_PORTALS_PATH = (
    Path(__file__).resolve().parent.parent / "hierarchies" / "communal_portals.yaml"
)


@lru_cache(maxsize=1)
def load_communal_portals() -> dict[int, CommunalPortal]:
    """Load the BFS -> portal registry from config (#632).

    The registry used to be a Python ``ClassVar`` dict, so adding commune #2 was
    a code change — contradicting this provider's own "adding a commune is a
    config change, not code" claim. It now lives in ``communal_portals.yaml``:
    editing that data file is all it takes to register a new commune.
    """
    with _COMMUNAL_PORTALS_PATH.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    portals_raw = payload.get("portals")
    if not isinstance(portals_raw, dict):
        raise ProviderConfigurationError(
            "communal_portals.yaml must contain a 'portals' mapping of BFS number -> portal."
        )
    portals: dict[int, CommunalPortal] = {}
    for bfs_raw, entry in portals_raw.items():
        try:
            bfs = int(bfs_raw)
        except (TypeError, ValueError) as exc:
            raise ProviderConfigurationError(
                f"communal_portals.yaml: BFS key {bfs_raw!r} is not an integer."
            ) from exc
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("host"), str)
            or not isinstance(entry.get("canton_jurisdiction_id"), str)
        ):
            raise ProviderConfigurationError(
                f"communal_portals.yaml: BFS {bfs} needs string 'host' and "
                "'canton_jurisdiction_id' fields."
            )
        portals[bfs] = CommunalPortal(
            host=entry["host"],
            canton_jurisdiction_id=entry["canton_jurisdiction_id"],
        )
    return portals


def _iso_date(raw: str | None) -> str | None:
    """Convert a Swiss `dd.mm.yyyy` date to ISO `yyyy-mm-dd`."""
    if not raw:
        return None
    match = _SWISS_DATE_RE.match(raw.strip())
    if not match:
        return None
    day, month, year = match.groups()
    return f"{year}-{month}-{day}"


def _read_field(payload: str, field: str) -> str | None:
    match = re.search(_FIELD_RE_TEMPLATE.format(field=field), payload, re.DOTALL)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def parse_amtliche_sammlung_page(html_text: str, *, page_url: str) -> dict[str, Any]:
    """Extract AS metadata + the operative-text manifestation from a landing page.

    Returns the AS number, title, the lifecycle dates (including
    `in_force_until`, which is empty while an enactment is still in force),
    and the resolved URL + content type of the operative text.
    """
    # The JSON payload is HTML-escaped inside an attribute; unescape twice
    # because the inner <a href> is itself escaped a second time.
    unescaped = html_module.unescape(html_module.unescape(html_text))

    as_number = None
    as_match = _AS_NUMBER_RE.search(unescaped)
    if as_match:
        as_number = as_match.group(1)

    title = None
    title_match = _TITLE_RE.search(html_text)
    if title_match:
        title = re.sub(r"\s+", " ", title_match.group(1)).strip()
        # Landing pages are titled "<Erlass> | Stadt Zürich".
        title = title.split("|", 1)[0].strip() or None

    document_url = None
    content_type = None
    rechtstexte = _read_field(unescaped, "rechtstexte")
    if rechtstexte:
        href_match = _MANIFESTATION_HREF_RE.search(rechtstexte)
        if href_match:
            href = href_match.group(1).strip()
            document_url = urljoin(page_url, href)
            suffix = href.rsplit(".", 1)[-1].lower()
            content_type = _CONTENT_TYPE_BY_SUFFIX.get(suffix)

    return {
        "as_number": as_number,
        "title": title,
        "decided_on": _iso_date(_read_field(unescaped, "erlassdatum")),
        "in_force_from": _iso_date(_read_field(unescaped, "inkrafttretendatum")),
        # Empty while the enactment is in force. This is the repeal/until date
        # ADR-0033 records as missing from the corpus — the municipal layer
        # publishes it, so it should survive into the document metadata.
        #
        # THE BOUNDARY (#843): **NOT MEASURED, and deliberately not guessed.**
        # Our `in_force_until` is the inclusive last day in force
        # (contracts/schemas/document.schema.json;
        # legal-search/api/src/core/norm-hierarchy/in-force.ts:24-28). Whether
        # Stadt Zürich's `ausserkrafttretendatum` agrees is unknown: the only AS
        # page held in this repo
        # (tests/fixtures/gemeinde_http/stadt_zuerich_as_554_510.html) has the
        # field EMPTY, and #843 found no repealed AS page anywhere in the tree to
        # compare against. `ris_ogd` and `fedlex_sparql` were measured inclusive
        # and `lexfind_api` exclusive, so the field name settles nothing — the
        # German is identical across all three and the readings are not.
        #
        # The value is therefore passed through unconverted, which is the
        # status-quo behaviour and the only defensible one: converting on a guess
        # would move a real date by a day on no evidence. The probe that would
        # settle it is a repealed Stadt-Zürich AS number whose successor's
        # `inkrafttretendatum` can be read off the next page — equal implies
        # exclusive, one day later implies inclusive.
        "in_force_until": _iso_date(_read_field(unescaped, "ausserkrafttretendatum")),
        "document_url": document_url,
        "document_content_type": content_type,
        "landing_page_url": page_url,
    }


class GemeindeHttpProvider:
    """Config-driven HTTP provider for Swiss communal legal collections."""

    provider_name = AcquisitionProvider.GEMEINDE_HTTP.value
    # Acquisition (#584) and normalisation (#650, ADR-0041) are done, and an
    # ADR-0030 acceptance run against live Zürich AS 554.510 on 2026-07-20
    # captured the evidence with every gate armed and none skipped (#735):
    # docs/runbooks/evidence/2026-07-20-ch-gemeinde-zuerich-acceptance.md
    #
    # This key says the code works. The config key — whether this corpus is
    # accepted — is the operator's, and the templates still ship `enabled: false`.
    #
    # If this is ever rolled back, roll back to SCAFFOLD, not AWAITING_EVIDENCE:
    # the latter is the one state whose acceptance runs waive the operator's
    # config key, so it would re-open the route a rollback is trying to close.
    readiness: ClassVar[AcquisitionReadiness] = AcquisitionReadiness.LIVE

    @property
    def supported_portals(self) -> dict[int, CommunalPortal]:
        """BFS/OFS Gemeindenummer → the commune's legal-collection portal.

        Backed by ``communal_portals.yaml`` (#632): seed URLs in a blueprint
        template must resolve to the registered host (or a subdomain), and
        `canton_jurisdiction_id` is the commune's parent canton for the ADR-0033
        norm-hierarchy walk. Zürich (261) is verified; registering further
        communes is a config edit to that data file, not a code change.
        """
        return load_communal_portals()

    async def start_run(
        self,
        source: Source,
        source_version: SourceVersion,
        run: Run,
    ) -> ProviderStartResult:
        del source
        acquisition_spec: dict[str, Any] = source_version.acquisition_spec or {}
        bfs_number = self._require_bfs_number(acquisition_spec)
        portal = self._portal(bfs_number)
        seed_urls = self._seed_urls(acquisition_spec, portal_host=portal.host)
        timeout_seconds = float(acquisition_spec.get("request_timeout_seconds") or 30.0)
        max_content_bytes = int(acquisition_spec.get("max_content_bytes") or 5_000_000)

        resources: list[ProviderResource] = []
        failures: list[dict[str, str]] = []
        # Manifestations we found but cannot carry through the text-only
        # acquisition interface. Surfaced so an acceptance run shows exactly
        # what a live-enabled provider *would* fetch.
        skipped: list[dict[str, Any]] = []

        async with httpx.AsyncClient(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": "evidara-gemeinde-http/1.0 (+https://evidara.ai/contact)"},
        ) as client:
            for url in seed_urls:
                try:
                    response = await limited_get(client, url)
                    response.raise_for_status()
                    body = response.content or b""
                    if len(body) > max_content_bytes:
                        body = body[:max_content_bytes]
                    if not body:
                        failures.append({"url": url, "error": "empty response body"})
                        continue
                    charset = response.charset_encoding or "utf-8"
                    body_text = body.decode(charset, errors="replace")

                    record = parse_amtliche_sammlung_page(body_text, page_url=str(response.url))
                    document_url = record.get("document_url")
                    content_type = record.get("document_content_type")

                    if document_url is None:
                        failures.append(
                            {
                                "url": url,
                                "error": _NO_MANIFESTATION_ERROR,
                            }
                        )
                        continue

                    if content_type not in _CARRIABLE_CONTENT_TYPES:
                        # Still refuse anything we cannot faithfully represent, rather
                        # than emit the metadata landing page as a stand-in for the
                        # ordinance. See module docstring.
                        skipped.append(
                            {
                                "url": document_url,
                                "content_type": content_type,
                                "reason": "unsupported_manifestation_content_type",
                                "as_number": record.get("as_number"),
                                "title": record.get("title"),
                                "in_force_from": record.get("in_force_from"),
                                "in_force_until": record.get("in_force_until"),
                            }
                        )
                        continue

                    text_response = await limited_get(client, document_url)
                    text_response.raise_for_status()
                    manifestation = (text_response.content or b"")[:max_content_bytes]
                    is_binary = content_type in _BINARY_CONTENT_TYPES
                    resources.append(
                        ProviderResource(
                            source_url=document_url,
                            final_url=str(text_response.url),
                            content_type=content_type,
                            # A PDF must travel as bytes: decoding it would corrupt the
                            # ordinance before it ever reached the normaliser (#590).
                            body=None
                            if is_binary
                            else manifestation.decode(
                                text_response.charset_encoding or "utf-8", errors="replace"
                            ),
                            body_bytes=manifestation if is_binary else None,
                            title=record.get("title"),
                            http_status=text_response.status_code,
                            discovery_depth=1,
                            metadata=self._resource_metadata(
                                record, bfs_number=bfs_number, portal=portal
                            ),
                        )
                    )
                except Exception as exc:  # pragma: no cover - defensive capture
                    failures.append({"url": url, "error": str(exc)})

        response_payload: dict[str, Any] = {
            "provider": self.provider_name,
            "requested": len(seed_urls),
            "captured": len(resources),
            "failed": len(failures),
            "skipped": len(skipped),
            "failures": failures,
            "skipped_manifestations": skipped,
            "bfs_number": bfs_number,
        }

        inline_failure_reason = None
        if not resources:
            if skipped:
                inline_failure_reason = (
                    f"{self.provider_name} found {len(skipped)} manifestation(s) for BFS "
                    f"{bfs_number}, none of which it can carry: the operative text was "
                    "neither HTML (-> body) nor a supported binary type (-> body_bytes). "
                    "PDF and HTML are both emitted as of #584/#590; this reports an "
                    "unrecognised content type rather than a missing capability."
                )
            else:
                # The per-URL reasons are already in `failures`; the operator only ever
                # saw the generic sentence below, which cannot distinguish "the seeds
                # are wrong" from "this portal is not a schema I can read" (#784). The
                # sibling branch above explains its case precisely; this one now does
                # too — the information was collected and then thrown away.
                unparsed = [f["url"] for f in failures if f.get("error") == _NO_MANIFESTATION_ERROR]
                if unparsed and len(unparsed) == len(failures):
                    inline_failure_reason = (
                        f"{self.provider_name} reached all {len(unparsed)} page(s) for BFS "
                        f"{bfs_number} but found no operative-text link on any of them. "
                        "Either these are not Amtliche-Sammlung-shaped landing pages, or "
                        "the commune publishes law in a layout this provider does not "
                        "parse. Adding a commune is a config change only where the portal "
                        "shares Zürich's page shape; a different shape needs a parser."
                    )
                else:
                    detail = "; ".join(f"{f.get('url')}: {f.get('error')}" for f in failures[:3])
                    suffix = f" (+{len(failures) - 3} more)" if len(failures) > 3 else ""
                    inline_failure_reason = (
                        f"{self.provider_name} did not capture any resources for BFS "
                        f"{bfs_number}" + (f" — {detail}{suffix}" if detail else "")
                    )

        return ProviderStartResult(
            provider=self.provider_name,
            external_job_id=f"{self.provider_name}_{run.run_id}",
            request_payload={
                "seed_urls": seed_urls,
                "bfs_number": bfs_number,
                "portal_host": portal.host,
            },
            response_payload=response_payload,
            inline_resources=resources,
            inline_failure_reason=inline_failure_reason,
        )

    def plan(self, source: Source, source_version: SourceVersion) -> ProviderPlan:
        """Describe the acquisition without network IO."""
        del source
        acquisition_spec: dict[str, Any] = source_version.acquisition_spec or {}
        notes: list[str] = []
        seed_urls: list[str] = []
        try:
            bfs_number = self._require_bfs_number(acquisition_spec)
            portal = self._portal(bfs_number)
            seed_urls = self._seed_urls(acquisition_spec, portal_host=portal.host)
            notes.append(f"bfs_number={bfs_number}")
            notes.append(f"jurisdiction=jur_ch_gemeinde_{bfs_number}")
            notes.append(f"canton={portal.canton_jurisdiction_id}")
            notes.append(f"portal_host={portal.host}")
        except ProviderConfigurationError as exc:
            notes.append(f"config_error={exc}")
        notes.append(
            "readiness=live: acquisition (#584) and PDF normalisation (#650) are done and "
            "evidenced against live Zürich AS 554.510 (2026-07-20, #735). The template "
            "still needs its config key enabled by an operator."
        )
        return ProviderPlan(
            provider=self.provider_name,
            seed_urls=seed_urls,
            estimated_request_count=len(seed_urls) * 2,  # landing page + operative text
            request_timeout_seconds=float(acquisition_spec.get("request_timeout_seconds") or 30.0),
            notes=notes,
            raw=dict(acquisition_spec),
        )

    # ─── Helpers ──────────────────────────────────────────────

    def _resource_metadata(
        self,
        record: dict[str, Any],
        *,
        bfs_number: int,
        portal: CommunalPortal,
    ) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "bfs_number": bfs_number,
            # The municipal document must carry its level and link to its
            # canton for the ADR-0033 norm-hierarchy walk (#583).
            "level": "municipal",
            "jurisdiction_id": f"jur_ch_gemeinde_{bfs_number}",
            "parent_jurisdiction_id": portal.canton_jurisdiction_id,
            "portal_host": portal.host,
            "as_number": record.get("as_number"),
            "decided_on": record.get("decided_on"),
            "in_force_from": record.get("in_force_from"),
            "in_force_until": record.get("in_force_until"),
            "landing_page_url": record.get("landing_page_url"),
            "fetched_at": datetime.now(UTC).isoformat(),
        }

    def _require_bfs_number(self, acquisition_spec: dict[str, Any]) -> int:
        raw = acquisition_spec.get("bfs_number")
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise ProviderConfigurationError(
                f"{self.provider_name} requires acquisition_spec.bfs_number "
                "(BFS/OFS Gemeindenummer, e.g. 261 for Zürich)"
            )
        return raw

    def _portal(self, bfs_number: int) -> CommunalPortal:
        portal = self.supported_portals.get(bfs_number)
        if portal is None:
            raise ProviderConfigurationError(
                f"{self.provider_name} has no supported portal for BFS {bfs_number}. "
                f"Supported: {sorted(self.supported_portals)}"
            )
        return portal

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
