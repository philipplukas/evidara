from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any, NamedTuple
from urllib.parse import urlparse

import httpx

from acquisition_core.content_gate import assess_legal_text_density
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

_FEDLEX_HOST = "fedlex.data.admin.ch"
_FEDLEX_FILESTORE_HOST = "www.fedlex.admin.ch"

# SCOPE: this provider acquires FEDERAL Swiss law only, from seed work URIs.
#
# It once carried a `canton_discovery` mode that enumerated works via a
# `jolux:CantonOfOrigin` predicate. That predicate never existed. Measured
# against the live endpoint on 2026-07-19 (#716): 56,238,852 triples, 426
# distinct predicates, ZERO containing "anton" (case-insensitive, so both
# `Canton` and `Kanton`); six spelling variants all `ASK -> false`; the
# vocabulary the IRIs were built against (`/vocabulary/canton/ZH`) 404s while
# the control `/vocabulary/legal-institution/3525` returns 200; 133 classes,
# none cantonal; only the federal collections `fga` (BBl), `oc` (AS) and `cc`
# (SR) are present.
#
# Fedlex is the Federal Chancellery platform for Bundesrecht. Cantonal law is
# out of scope by design — each canton runs its own systematic collection. The
# inter-cantonal concordats Fedlex *does* carry are modelled as AS-collection
# publications with no cantonal attribution of any kind, so they cannot be
# filtered by canton either. Do not re-add a cantonal mode here: cantonal
# coverage needs a per-canton provider against the canton's own portal.

# jolux predicates that carry a consolidation's entry-into-force window.
# VERIFIED against the live endpoint (https://fedlex.data.admin.ch/sparqlendpoint,
# 2026-07-17, issue #633): each `jolux:isMemberOf` consolidation of a work exposes
# `jolux:dateApplicability` (first day the consolidation is in force) and, when the
# consolidation has been superseded, `jolux:dateEndApplicability` (last day in
# force). The current/open consolidation may omit the end date. These are the only
# two predicates the selection + temporal-metadata logic depends on; if Fedlex ever
# renames them, correct them here and nowhere else.
_JOLUX_IN_FORCE_FROM_PREDICATE = "jolux:dateApplicability"
_JOLUX_IN_FORCE_UNTIL_PREDICATE = "jolux:dateEndApplicability"

# Act-level (abstract work) temporal predicates. VERIFIED against the live endpoint
# (2026-07-19, issue #628): the abstract work carries `jolux:inForceStatus` (a
# fedlex `enforcement-status` vocabulary IRI) and `jolux:dateEntryInForce` (the
# act's original entry into force, distinct from the selected consolidation's
# applicability date).
#
# Why this matters beyond the consolidation window: a repealed act's newest
# consolidation does NOT always carry `dateEndApplicability`. Measured live, 3
# works with status "no longer in force" have an open-ended newest consolidation
# — so consolidation dates alone would report repealed law as currently in force.
# That is exactly the confident fabrication ADR-0033 exists to prevent, so the
# act-level status is authoritative over an absent end date.
_JOLUX_IN_FORCE_STATUS_PREDICATE = "jolux:inForceStatus"
_JOLUX_ENTRY_IN_FORCE_PREDICATE = "jolux:dateEntryInForce"

# https://fedlex.data.admin.ch/vocabulary/enforcement-status/{code} → our value.
# Confirmed live: only 0, 1 and 3 are in use, with skos:prefLabel@en as noted.
_ENFORCEMENT_STATUS_BY_CODE = {
    "0": "in_force",  # "In force"
    "1": "no_longer_published",  # "No longer published in the SR"
    "3": "no_longer_in_force",  # "No longer in force"
}
_ENFORCEMENT_STATUS_VOCABULARY = "https://fedlex.data.admin.ch/vocabulary/enforcement-status/"


class _ConsolidationMember(NamedTuple):
    """A single dated consolidation of a Fedlex work.

    `uri` is the concrete (dated) work URI, e.g.
    `https://fedlex.data.admin.ch/eli/cc/1999/404/20240303`. `in_force_from` /
    `in_force_until` are the parsed jolux applicability dates and are None when the
    endpoint does not publish them for this member.
    """

    uri: str
    in_force_from: date | None
    in_force_until: date | None


def _parse_sparql_date(binding: object) -> date | None:
    """Parse a SPARQL JSON binding carrying an xsd:date into a `date`.

    Fedlex publishes applicability dates as `xsd:date` literals (`2024-03-03`).
    Some values arrive as `xsd:dateTime`; take the leading date component. Returns
    None for an absent or unparseable binding — the caller treats missing dates as
    "temporal validity unknown" rather than guessing.
    """
    if not isinstance(binding, dict):
        return None
    value = binding.get("value")
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    # Tolerate `xsd:dateTime` (`2024-03-03T00:00:00+02:00`) by keeping the date part.
    date_part = text.split("T", 1)[0]
    try:
        return date.fromisoformat(date_part)
    except ValueError:
        return None


def _iso_date_or_none(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


class FedlexSparqlProvider:
    provider_name = AcquisitionProvider.FEDLEX_SPARQL.value
    readiness = AcquisitionReadiness.LIVE
    _EXPRESSION_QUERY = """
PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
SELECT ?expr
WHERE {{
  <{work_uri}> jolux:isRealizedBy ?expr .
}}
ORDER BY ?expr
""".strip()

    # The consolidation members of a work, each with its entry-into-force window.
    # The applicability dates drive which consolidation is "in force" as-of a
    # requested date (#633) — taking the newest member unconditionally acquired a
    # future consolidation ("Stand am 1. Januar 2029"). `ORDER BY ?member` keeps a
    # deterministic order for the no-dates fallback path.
    _MEMBER_QUERY = """
PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
SELECT ?member ?inForceFrom ?inForceUntil
WHERE {{
  ?member jolux:isMemberOf <{work_uri}> .
  OPTIONAL {{ ?member {in_force_from_predicate} ?inForceFrom . }}
  OPTIONAL {{ ?member {in_force_until_predicate} ?inForceUntil . }}
}}
ORDER BY ?member
""".strip()

    # Act-level enforcement status + original entry into force, read from the
    # abstract work (not the consolidation). Both are OPTIONAL: older works may
    # publish neither, in which case the temporal answer stays whatever the
    # consolidation window said.
    _WORK_STATUS_QUERY = """
PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
SELECT ?status ?entryIntoForce
WHERE {{
  OPTIONAL {{ <{work_uri}> {status_predicate} ?status . }}
  OPTIONAL {{ <{work_uri}> {entry_in_force_predicate} ?entryIntoForce . }}
}}
LIMIT 1
""".strip()

    _TITLE_QUERY = """
PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
SELECT ?title ?titleShort
WHERE {{
  <{expression_uri}> jolux:title ?title .
  OPTIONAL {{ <{expression_uri}> jolux:titleShort ?titleShort . }}
}}
LIMIT 1
""".strip()

    async def start_run(
        self,
        source: Source,
        source_version: SourceVersion,
        run: Run,
    ) -> ProviderStartResult:
        del source
        acquisition_spec = source_version.acquisition_spec or {}
        sparql_endpoint = self._validate_fedlex_url(
            str(acquisition_spec.get("sparql_endpoint") or f"https://{_FEDLEX_HOST}/sparqlendpoint")
        )
        preferred_languages = self._preferred_languages(acquisition_spec)
        max_expressions = int(acquisition_spec.get("max_expressions") or 1)
        timeout_seconds = float(acquisition_spec.get("request_timeout_seconds") or 30.0)
        max_content_bytes = int(acquisition_spec.get("max_content_bytes") or 2_000_000)
        # The consolidation in force at this date is selected — default today, so a
        # future consolidation is never acquired unless an operator opts in with an
        # explicit `as_of_date` (#633).
        as_of = self._as_of_date(acquisition_spec)

        resources: list[ProviderResource] = []
        failures: list[dict[str, str]] = []
        # Manifestations fetched and refused by the legal-text density gate: a 200
        # carrying chrome rather than the act. Recorded, never counted as captured
        # (#631). Same shape as `portal_http_provider_base`'s.
        skipped: list[dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
            work_uris = self._seed_work_uris(acquisition_spec)

            for work_uri in work_uris:
                try:
                    selected_member, member_in_force = await self._resolve_concrete_work(
                        client=client,
                        sparql_endpoint=sparql_endpoint,
                        work_uri=work_uri,
                        as_of=as_of,
                    )
                    concrete_work_uri = selected_member.uri
                    # Act-level status is authoritative over an absent
                    # consolidation end date: a repealed act whose newest
                    # consolidation is open-ended would otherwise be reported as
                    # currently in force (measured live: 3 such works).
                    in_force_status, entry_into_force = await self._query_work_status(
                        client=client,
                        sparql_endpoint=sparql_endpoint,
                        work_uri=work_uri,
                    )
                    if in_force_status == "no_longer_in_force":
                        member_in_force = False
                    expression_uris = await self._query_expression_uris(
                        client=client,
                        sparql_endpoint=sparql_endpoint,
                        work_uri=concrete_work_uri,
                    )
                    selected_expression_uris = self._select_expression_uris(
                        expression_uris=expression_uris,
                        preferred_languages=preferred_languages,
                        max_expressions=max_expressions,
                    )
                    describe_turtle = await self._describe_graph(
                        client=client,
                        sparql_endpoint=sparql_endpoint,
                        work_uri=concrete_work_uri,
                        expression_uris=selected_expression_uris,
                        max_content_bytes=max_content_bytes,
                    )
                    title, title_short = await self._query_title(
                        client=client,
                        sparql_endpoint=sparql_endpoint,
                        expression_uris=selected_expression_uris,
                    )
                    html_url = self._filestore_html_url(
                        selected_expression_uris[0],
                        concrete_work_uri,
                    )
                    resolved_url, response, body = await self._fetch_text_manifestation(
                        client=client,
                        url=html_url,
                        max_content_bytes=max_content_bytes,
                    )
                    content_type = (
                        response.headers.get("content-type", "text/html")
                        .split(";", 1)[0]
                        .strip()
                        .lower()
                    )
                    charset = response.charset_encoding or "utf-8"
                    if not body:
                        raise ProviderConfigurationError(
                            f"fedlex_sparql manifestation response was empty for {html_url}"
                        )
                    body_text = body.decode(charset, errors="replace")

                    # The legal-text density gate (#631). `scripts/ch-fedlex-fast-loop.sh`
                    # has gated on `art_density >= 3` against THIS provider's output since
                    # the canary was written, and #635 lifted that heuristic into
                    # `content_gate` so every provider could share it — but the sharing
                    # never reached the provider the heuristic came from. Until this call
                    # existed the check ran only in a canary script an operator has to
                    # remember to run, so a Fedlex filestore error page or holding page
                    # was capturable by the acquisition path itself.
                    assessment = assess_legal_text_density(body_text, content_type=content_type)
                    if not assessment.is_legal_text:
                        skipped.append(
                            {
                                "url": resolved_url,
                                "work_uri": work_uri,
                                "reason": "no_legal_text_markers",
                                "detail": assessment.reason,
                                **assessment.as_evidence(),
                            }
                        )
                        continue

                    html_title = self._title_from_html(body_text)
                    resources.append(
                        ProviderResource(
                            source_url=work_uri,
                            final_url=resolved_url,
                            content_type=content_type,
                            body=body_text,
                            title=title or html_title or title_short or work_uri.rsplit("/", 1)[-1],
                            http_status=response.status_code,
                            discovery_depth=0,
                            metadata={
                                "provider": self.provider_name,
                                "sparql_endpoint": sparql_endpoint,
                                "concrete_work_uri": concrete_work_uri,
                                "expression_uris": selected_expression_uris,
                                "manifestation_url": resolved_url,
                                "title": (
                                    title
                                    or html_title
                                    or title_short
                                    or work_uri.rsplit("/", 1)[-1]
                                ),
                                "title_short": title_short,
                                "describe_turtle": describe_turtle,
                                "fetched_at": datetime.now(UTC).isoformat(),
                                # The gate's verdict travels with the document, so
                                # acceptance evidence shows the check ran rather
                                # than leaving it inferred from a passing count.
                                "legal_text_assessment": "passed",
                                "legal_text_evidence": assessment.as_evidence(),
                                # ELI round-trip: Fedlex work URIs ARE ELI URIs.
                                # Emitting eli_uri here lets canonical document
                                # metadata carry the identifier forward per
                                # docs/architecture/vocabulary-standards.md.
                                "eli_uri": self._eli_uri_for_work(work_uri, concrete_work_uri),
                                # Temporal validity of the selected consolidation
                                # (#633). Same metadata keys the gemeinde_http
                                # provider emits, so downstream in-force logic can
                                # answer instead of reporting `unknown`. None when
                                # Fedlex does not publish an applicability date
                                # (the current consolidation omits an end date).
                                "in_force_from": _iso_date_or_none(selected_member.in_force_from),
                                "in_force_until": _iso_date_or_none(selected_member.in_force_until),
                                # Provenance for the selection itself: which date we
                                # asked "what is in force?" for, and whether the
                                # chosen consolidation actually covers it. `False`
                                # means the corpus would hold law not in force as-of
                                # `selected_as_of` — the canary gates on this.
                                "selected_as_of": as_of.isoformat(),
                                "in_force_at_selection": member_in_force,
                                # Act-level signals (#628). `in_force_status` is
                                # the fedlex enforcement-status vocabulary term
                                # for the whole act; `entry_into_force` is the
                                # act's original entry into force, which differs
                                # from the selected consolidation's start date.
                                # Both None when Fedlex publishes neither.
                                "in_force_status": in_force_status,
                                "entry_into_force": _iso_date_or_none(entry_into_force),
                            },
                        )
                    )
                except Exception as exc:  # pragma: no cover - defensive capture path
                    failures.append({"url": work_uri, "error": str(exc)})

        response_payload = {
            "provider": self.provider_name,
            "requested": len(work_uris),
            "captured": len(resources),
            "failed": len(failures),
            "skipped": len(skipped),
            "failures": failures,
            "skipped_documents": skipped,
        }
        inline_failure_reason = None
        if not resources:
            if skipped:
                inline_failure_reason = (
                    f"fedlex_sparql fetched {len(skipped)} manifestation(s) but all failed "
                    "the legal-text density gate: the filestore returned a page with no "
                    "Art./§/Abs. markers, which is chrome or an error page rather than the "
                    "act. Refusing rather than capturing it as acceptance evidence (#631)."
                )
            else:
                inline_failure_reason = "Fedlex SPARQL provider did not capture any resources."

        return ProviderStartResult(
            provider=self.provider_name,
            external_job_id=f"fedlexsparql_{run.run_id}",
            request_payload={
                "work_uris": work_uris,
                "sparql_endpoint": sparql_endpoint,
                "preferred_languages": preferred_languages,
                "max_expressions": max_expressions,
                "manifestation_format": "html",
                "as_of_date": as_of.isoformat(),
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
        max_expressions = int(acquisition_spec.get("max_expressions") or 1)
        sparql_endpoint = str(
            acquisition_spec.get("sparql_endpoint") or f"https://{_FEDLEX_HOST}/sparqlendpoint"
        )
        work_uris = self._seed_work_uris(acquisition_spec)
        return ProviderPlan(
            provider=self.provider_name,
            mode="work_to_expression",
            seed_urls=work_uris,
            estimated_request_count=len(work_uris) * max_expressions,
            user_agent=acquisition_spec.get("user_agent"),
            request_timeout_seconds=float(acquisition_spec.get("request_timeout_seconds") or 30.0),
            notes=[f"sparql_endpoint={sparql_endpoint}"],
            raw=dict(acquisition_spec),
        )

    def _seed_work_uris(self, acquisition_spec: dict[str, object]) -> list[str]:
        seed_urls = [
            str(url)
            for url in acquisition_spec.get("seed_urls", [])
            if isinstance(url, str) and url.strip()
        ]
        seed_url = acquisition_spec.get("seed_url")
        if isinstance(seed_url, str) and seed_url.strip():
            seed_urls.append(seed_url)

        unique_uris: list[str] = []
        seen: set[str] = set()
        for url in seed_urls:
            validated = self._validate_fedlex_url(url)
            if validated in seen:
                continue
            unique_uris.append(validated)
            seen.add(validated)
        if not unique_uris:
            raise ProviderConfigurationError(
                "fedlex_sparql provider requires acquisition_spec.seed_url or seed_urls."
            )
        return unique_uris

    def _preferred_languages(self, acquisition_spec: dict[str, object]) -> list[str]:
        raw = acquisition_spec.get("preferred_languages")
        if isinstance(raw, list):
            languages = [str(item).strip().lower() for item in raw if str(item).strip()]
        else:
            fallback = acquisition_spec.get("language_codes")
            languages = [
                str(item).strip().lower()[:2] for item in fallback or [] if str(item).strip()
            ]
        return [language for language in languages if language]

    def _eli_uri_for_work(self, seed_work_uri: str, concrete_work_uri: str) -> str | None:
        """Return the ELI URI for a Fedlex work, preferring the abstract form.

        Fedlex work URIs are already ELI URIs (e.g.
        `https://fedlex.data.admin.ch/eli/cc/1999/404`). The `concrete_work_uri`
        carries a dated temporal selector (e.g. `.../404/20240303`) — we prefer
        the abstract `seed_work_uri` so the emitted identifier matches the
        canonical ELI shape used by external ELI consumers. Returns None if
        neither URI looks like a Fedlex ELI URI.
        """
        for candidate in (seed_work_uri, concrete_work_uri):
            if isinstance(candidate, str) and f"{_FEDLEX_HOST}/eli/" in candidate:
                return candidate
        return None

    def _as_of_date(self, acquisition_spec: dict[str, object]) -> date:
        """Return the date at which "in force" is evaluated for this run.

        Defaults to today (UTC). An operator can pin an explicit `as_of_date`
        (ISO `YYYY-MM-DD`) in the acquisition spec to intentionally acquire a
        consolidation in force at another date — including a future one. Making
        future acquisition an explicit, auditable act is the whole point of #633:
        the default must never reach past today.
        """
        raw = acquisition_spec.get("as_of_date")
        if isinstance(raw, str) and raw.strip():
            try:
                return date.fromisoformat(raw.strip())
            except ValueError as exc:
                raise ProviderConfigurationError(
                    f"fedlex_sparql acquisition_spec.as_of_date must be ISO YYYY-MM-DD: {raw!r}"
                ) from exc
        return datetime.now(UTC).date()

    async def _resolve_concrete_work(
        self,
        *,
        client: httpx.AsyncClient,
        sparql_endpoint: str,
        work_uri: str,
        as_of: date,
    ) -> tuple[_ConsolidationMember, bool]:
        """Resolve the work URI to the consolidation in force at `as_of`.

        Returns the selected `_ConsolidationMember` and whether it is actually in
        force at `as_of`. When the work has no members, the abstract work URI is
        returned unchanged (in_force flag True — nothing to assert against).
        """
        members = await self._query_consolidation_members(
            client=client,
            sparql_endpoint=sparql_endpoint,
            work_uri=work_uri,
        )
        if not members:
            return _ConsolidationMember(uri=work_uri, in_force_from=None, in_force_until=None), True
        return self._select_consolidation_member(members=members, as_of=as_of)

    def _select_consolidation_member(
        self,
        *,
        members: list[_ConsolidationMember],
        as_of: date,
    ) -> tuple[_ConsolidationMember, bool]:
        """Pick the consolidation in force at `as_of`, never a future one.

        The consolidation in force at a date is the newest one whose
        `in_force_from` has already arrived by that date; it is *in force* when its
        `in_force_until` has not yet passed (or is open-ended). A future
        consolidation (`in_force_from > as_of`) is only reachable by moving `as_of`
        forward — it is never selected for a past/present `as_of`.

        When no member carries applicability dates (endpoint variation), the
        temporal question cannot be answered, so fall back to the newest member by
        URI (previous behaviour) and report in-force as unknown-but-not-false.
        """
        dated = [member for member in members if member.in_force_from is not None]
        if not dated:
            return members[-1], True
        applicable = [member for member in dated if member.in_force_from <= as_of]
        if applicable:
            selected = max(applicable, key=lambda member: member.in_force_from)
            in_force = selected.in_force_until is None or selected.in_force_until >= as_of
            return selected, in_force
        # `as_of` precedes every consolidation: the law did not yet exist then.
        # Return the earliest so the caller still has a concrete URI, flagged
        # not-in-force so the acceptance gate can refuse it.
        earliest = min(dated, key=lambda member: member.in_force_from)
        return earliest, False

    async def _query_work_status(
        self,
        *,
        client: httpx.AsyncClient,
        sparql_endpoint: str,
        work_uri: str,
    ) -> tuple[str | None, date | None]:
        """Read the act-level enforcement status and original entry into force.

        Returns `(status, entry_into_force)` where `status` is one of
        `in_force` / `no_longer_in_force` / `no_longer_published`, or None when
        Fedlex publishes no status for this work (or publishes a vocabulary code
        we do not recognise — an unknown code is reported as None rather than
        being mapped onto a guess).
        """
        response = await limited_get(
            client,
            sparql_endpoint,
            params={
                "query": self._WORK_STATUS_QUERY.format(
                    work_uri=work_uri,
                    status_predicate=_JOLUX_IN_FORCE_STATUS_PREDICATE,
                    entry_in_force_predicate=_JOLUX_ENTRY_IN_FORCE_PREDICATE,
                ),
                "format": "application/sparql-results+json",
            },
            headers={"Accept": "application/sparql-results+json"},
        )
        response.raise_for_status()
        payload = response.json()
        bindings = payload.get("results", {}).get("bindings", [])
        if not bindings:
            return None, None
        binding = bindings[0]
        entry_into_force = _parse_sparql_date(binding.get("entryIntoForce"))
        status_value = binding.get("status", {})
        status_iri = status_value.get("value") if isinstance(status_value, dict) else None
        if not isinstance(status_iri, str) or not status_iri.startswith(
            _ENFORCEMENT_STATUS_VOCABULARY
        ):
            return None, entry_into_force
        code = status_iri[len(_ENFORCEMENT_STATUS_VOCABULARY) :].strip("/")
        return _ENFORCEMENT_STATUS_BY_CODE.get(code), entry_into_force

    async def _query_consolidation_members(
        self,
        *,
        client: httpx.AsyncClient,
        sparql_endpoint: str,
        work_uri: str,
    ) -> list[_ConsolidationMember]:
        response = await limited_get(
            client,
            sparql_endpoint,
            params={
                "query": self._MEMBER_QUERY.format(
                    work_uri=work_uri,
                    in_force_from_predicate=_JOLUX_IN_FORCE_FROM_PREDICATE,
                    in_force_until_predicate=_JOLUX_IN_FORCE_UNTIL_PREDICATE,
                ),
                "format": "application/sparql-results+json",
            },
            headers={"Accept": "application/sparql-results+json"},
        )
        response.raise_for_status()
        payload = response.json()
        bindings = payload.get("results", {}).get("bindings", [])
        members: list[_ConsolidationMember] = []
        for binding in bindings:
            member = binding.get("member", {}).get("value")
            if not (isinstance(member, str) and member.startswith(f"https://{_FEDLEX_HOST}/")):
                continue
            members.append(
                _ConsolidationMember(
                    uri=member,
                    in_force_from=_parse_sparql_date(binding.get("inForceFrom")),
                    in_force_until=_parse_sparql_date(binding.get("inForceUntil")),
                )
            )
        return members

    async def _query_expression_uris(
        self,
        *,
        client: httpx.AsyncClient,
        sparql_endpoint: str,
        work_uri: str,
    ) -> list[str]:
        response = await limited_get(
            client,
            sparql_endpoint,
            params={
                "query": self._EXPRESSION_QUERY.format(work_uri=work_uri),
                "format": "application/sparql-results+json",
            },
            headers={"Accept": "application/sparql-results+json"},
        )
        response.raise_for_status()
        payload = response.json()
        bindings = payload.get("results", {}).get("bindings", [])
        expression_uris: list[str] = []
        for binding in bindings:
            expr = binding.get("expr", {}).get("value")
            if isinstance(expr, str) and expr.startswith(f"https://{_FEDLEX_HOST}/"):
                expression_uris.append(expr)
        return expression_uris

    def _select_expression_uris(
        self,
        *,
        expression_uris: list[str],
        preferred_languages: list[str],
        max_expressions: int,
    ) -> list[str]:
        if not expression_uris:
            return []
        if preferred_languages:
            preferred_matches = [
                expr
                for language in preferred_languages
                for expr in expression_uris
                if expr.rstrip("/").endswith(f"/{language}")
            ]
            deduped = list(dict.fromkeys(preferred_matches))
            if deduped:
                return deduped[:max_expressions]
        return expression_uris[:max_expressions]

    async def _describe_graph(
        self,
        *,
        client: httpx.AsyncClient,
        sparql_endpoint: str,
        work_uri: str,
        expression_uris: list[str],
        max_content_bytes: int,
    ) -> str:
        targets = " ".join(f"<{uri}>" for uri in [work_uri, *expression_uris])
        query = f"DESCRIBE {targets}"
        response = await limited_get(
            client,
            sparql_endpoint,
            params={"query": query},
            headers={"Accept": "text/turtle"},
        )
        response.raise_for_status()
        body = await self._read_body_limited(response=response, max_content_bytes=max_content_bytes)
        if body is None:
            raise ProviderConfigurationError(
                f"fedlex_sparql response exceeded max_content_bytes={max_content_bytes}"
            )
        return body.decode(response.charset_encoding or "utf-8", errors="replace")

    async def _query_title(
        self,
        *,
        client: httpx.AsyncClient,
        sparql_endpoint: str,
        expression_uris: list[str],
    ) -> tuple[str | None, str | None]:
        candidate_uris: list[str] = []
        for expression_uri in expression_uris:
            candidate_uris.append(expression_uri)
            abstract_expression_uri = self._abstract_expression_uri(expression_uri)
            if abstract_expression_uri is not None:
                candidate_uris.append(abstract_expression_uri)
        for expression_uri in dict.fromkeys(candidate_uris):
            response = await limited_get(
                client,
                sparql_endpoint,
                params={
                    "query": self._TITLE_QUERY.format(expression_uri=expression_uri),
                    "format": "application/sparql-results+json",
                },
                headers={"Accept": "application/sparql-results+json"},
            )
            response.raise_for_status()
            bindings = response.json().get("results", {}).get("bindings", [])
            if bindings:
                row = bindings[0]
                title = row.get("title", {}).get("value")
                title_short = row.get("titleShort", {}).get("value")
                return (
                    title if isinstance(title, str) else None,
                    title_short if isinstance(title_short, str) else None,
                )
        return None, None

    async def _fetch_text_manifestation(
        self,
        *,
        client: httpx.AsyncClient,
        url: str,
        max_content_bytes: int,
    ) -> tuple[str, httpx.Response, bytes]:
        response = await limited_get(client, url, headers={"Accept": "text/html"})
        response.raise_for_status()
        body = await self._read_body_limited(response=response, max_content_bytes=max_content_bytes)
        if body is None:
            raise ProviderConfigurationError(
                f"fedlex_sparql manifestation exceeded max_content_bytes={max_content_bytes}"
            )
        return str(response.url), response, body

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

    def _validate_fedlex_url(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != _FEDLEX_HOST:
            raise ProviderConfigurationError(
                f"fedlex_sparql provider only supports https://{_FEDLEX_HOST} URLs: {url}"
            )
        return url

    def _filestore_html_url(self, expression_uri: str, concrete_work_uri: str) -> str:
        expression = self._validate_fedlex_url(expression_uri)
        concrete_work = self._validate_fedlex_url(concrete_work_uri)
        expression_parts = urlparse(expression).path.strip("/").split("/")
        work_parts = urlparse(concrete_work).path.strip("/").split("/")
        if len(expression_parts) < 6 or len(work_parts) < 5:
            raise ProviderConfigurationError(
                f"fedlex_sparql could not derive filestore HTML path from {expression_uri}"
            )
        path_parts = work_parts + [expression_parts[-1], "html"]
        filename = "-".join(["fedlex", "data", "admin", "ch", *path_parts]) + ".html"
        return (
            f"https://{_FEDLEX_FILESTORE_HOST}/filestore/fedlex.data.admin.ch/"
            f"{'/'.join(path_parts)}/{filename}"
        )

    def _abstract_expression_uri(self, expression_uri: str) -> str | None:
        expression = self._validate_fedlex_url(expression_uri)
        parts = urlparse(expression).path.strip("/").split("/")
        if len(parts) < 6 or not parts[-2].isdigit():
            return None
        abstract_parts = parts[:-2] + [parts[-1]]
        return f"https://{_FEDLEX_HOST}/{'/'.join(abstract_parts)}"

    def _title_from_html(self, body: str) -> str | None:
        h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", body, flags=re.IGNORECASE | re.DOTALL)
        if h1_match:
            title = re.sub(r"<[^>]+>", " ", h1_match.group(1))
            normalized = " ".join(title.split()).strip()
            if normalized:
                return normalized
        title_match = re.search(r"<title[^>]*>(.*?)</title>", body, flags=re.IGNORECASE | re.DOTALL)
        if title_match:
            normalized = " ".join(title_match.group(1).split()).strip()
            if normalized and not normalized.lower().startswith("input-"):
                return normalized
        return None
