#!/usr/bin/env python3
"""Survey Swiss communal legal-collection portals — what would each one cost to acquire? (#736)

WHY THIS EXISTS
---------------
`gemeinde_http` is one parser for one commune (Zürich). Extending the municipal rung
means knowing what the other 2,109 actually run, and nobody knows: every
`law_collection` block in `country-overlays/ch/municipalities.yaml` records a
publisher and a format and then says "URL to be confirmed". A DNS sweep on
2026-07-21 found 43 communes on LexWork/tlex — 2%, clustered by canton — which
ruled out "one parser covers it" without saying what the rest run.

This produces the table that answers it: per commune, a discovered collection URL,
a platform fingerprint, whether structured data is available, and what the operative
text is published as.

THREE PHASES, CHEAPEST FIRST
----------------------------
The LLM is the last resort, not the first. Most of the signal is deterministic and
free, and a fingerprint is a fact where a classification is an opinion.

  A. discover  — Wikidata's official website (P856, keyed by BFS number) plus DNS
                 guessing as a fallback. No page fetches, no cost, no load on anyone.
  B. fingerprint — one polite HTTP GET per candidate path. Vendor markers, `generator`
                 meta, JSON-LD / RDFa / ELI, link shapes (PDF vs HTML).
  B2. sitemap  — when no guessed path hits, ask the site to enumerate itself
                 (`sitemap.xml`, or whatever `robots.txt` declares). One or two
                 requests where a depth-2 crawl would cost ~70, and it answers the
                 question a crawl cannot: a complete sitemap containing no collection
                 page is evidence the commune publishes none.
  C. classify  — LLM, ONLY for pages phase B could not resolve. Structured output,
                 and every field must carry a verbatim `evidence` span from the page.
                 A classification without evidence is recorded as unknown, never
                 guessed — the ADR-0033 rule that a plausible value is worse than
                 an absent one applies to this survey too.

POLITENESS
----------
These are ~2,000 small government sites. Defaults: one request per host, 1.5s
between requests, robots.txt honoured, identifiable User-Agent, on-disk cache so a
re-run costs nobody anything. `--all` is required to go past `--limit`; the default
is a 50-commune pilot so nobody sweeps 2,110 sites by accident.

RESUMABILITY
------------
Every result is appended to a JSONL checkpoint keyed by BFS number. Re-running skips
what is already done, so a 2,110-row survey can be stopped and resumed.

That skip is a trap after a discovery fix: the rows a fix is aimed at are precisely
the ones already marked done, so a plain resume can never reach them. `--reprobe`
re-runs rows whose outcome carries no finding (`undiscovered`, `not_probed`, `error`)
and leaves confirmed hits alone. Last write wins per BFS number, so the superseded
row stays on disk as history.

OUTCOMES
--------
Three ways of finding nothing, and they are not interchangeable:

  not_probed              phase A resolved nothing, so no request was ever made.
  undiscovered            every URL in the budget was requested, none returned 200,
                          and the site offered no usable sitemap. Genuinely unknown.
  no_collection_published the site enumerated all its pages and not one is a legal
                          collection. This is an ANSWER — the commune cannot be
                          acquired by scraping because there is nothing to scrape —
                          and it is excluded from `--reprobe` for that reason.

Collapsing the first two is how the 2026-07-21 pilot reported 919 `undiscovered`
communes while never contacting 137 of them. Collapsing the third into `undiscovered`
would hide the survey's most useful result behind its least useful one: Muhen's
sitemap lists all 161 of its pages and none of them is a Reglemente section, which is
worth knowing and is not a gap to be probed harder.

USAGE
-----
    # pilot, no API key needed — phases A+B only
    uv run --with pyyaml,httpx python scripts/survey_communal_portals.py --limit 50

    # re-probe barren rows after a discovery fix, keeping confirmed hits
    uv run --with pyyaml,httpx python scripts/survey_communal_portals.py \\
        --all --reprobe

    # full run with the LLM phase
    OPENAI_API_KEY=... uv run --with pyyaml,httpx,openai,instructor \\
        python scripts/survey_communal_portals.py --all --classify

    # render the table from an existing checkpoint (no network)
    uv run --with pyyaml python scripts/survey_communal_portals.py --report
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import sys
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

REPO_ROOT = Path(__file__).resolve().parent.parent
MUNICIPALITIES = REPO_ROOT / "country-overlays" / "ch" / "municipalities.yaml"
DEFAULT_CHECKPOINT = (
    REPO_ROOT / "docs" / "runbooks" / "evidence" / "communal-portal-survey.jsonl"
)

USER_AGENT = (
    "EvidaraPortalSurvey/1.0 (+https://github.com/philipplukas/evidara; "
    "legal-corpus coverage research; contact via repository issues)"
)
REQUEST_DELAY_SECONDS = 1.5
# Cap on HTTP probes per commune before giving up and deferring to the agent pass.
# Raised 8 -> 12 once `probe_urls` started ordering breadth-first: at 8, with the old
# depth-first order, the budget was spent entirely on candidate domain 1 and the two
# French paths at the end of COLLECTION_PATHS were unreachable for every commune in
# the country. The cap is a politeness budget, so it buys coverage only because the
# ordering now spends it across domains and puts the likely path first.
MAX_HTTP_ATTEMPTS = 12
REQUEST_TIMEOUT_SECONDS = 8

# Vendors that host communes as per-tenant subdomains. Confirmed for tlex on
# 2026-07-21 (43 tenants, no wildcard DNS). The others are candidates to test —
# an empty result for one of them is itself a finding worth recording.
VENDOR_SUBDOMAIN_SUFFIXES = {
    "tlex": ".tlex.ch",
    "lexwork_naz": ".lexwork.naz.ch",
    "weblaw": ".weblaw.ch",
}

# Paths a Swiss commune commonly publishes its collection under, per language.
# Ordered by how often they appeared in manual inspection; the first 200 wins.
#
# These used to be one flat tuple with the French paths last, which — combined with a
# truncating probe budget — meant they were never requested even once. Keying by the
# `primary_language` already on every row makes a Romandy commune probe French paths
# first, and makes "we never tried" impossible to confuse with "there is nothing there".
COLLECTION_PATHS_BY_LANGUAGE = {
    "de": (
        "/rechtssammlung",
        "/erlasssammlung",
        "/erlass-sammlung",
        "/gesetzessammlung",
        "/reglemente",
        "/themen/die-stadt/erlass-sammlung",
        "/politik/reglemente",
        "/verwaltung/reglemente",
    ),
    "fr": (
        "/recueil-systematique",
        "/reglements",
        "/reglements-communaux",
        "/administration/reglements",
        "/officiel/reglements",
        "/recueil-communal",
    ),
    "it": (
        "/regolamenti",
        "/raccolta-leggi",
        "/ordinanze",
        "/amministrazione/regolamenti",
    ),
}
# Probed after the language's own paths, so a commune on the language border is still
# reachable. `rm` (Romansh) communes publish in German in practice and fall through here.
FALLBACK_COLLECTION_PATHS = (
    "/rechtssammlung",
    "/reglemente",
    "/recueil-systematique",
    "/reglements",
)


def collection_paths(language: str) -> tuple[str, ...]:
    """Paths to probe for a commune, most likely first."""
    primary = COLLECTION_PATHS_BY_LANGUAGE.get((language or "").lower(), ())
    ordered = list(primary)
    ordered.extend(p for p in FALLBACK_COLLECTION_PATHS if p not in primary)
    return tuple(ordered)


# Deterministic fingerprints. A match here is a fact; anything that reaches the LLM
# phase is one of these having failed.
VENDOR_MARKERS = (
    ("tlex/LexWork", re.compile(r"tlex\.ch|lexwork|texts_of_law", re.I)),
    ("CMI Axioma", re.compile(r"cmiaxioma|cmi\.ch", re.I)),
    ("Localcities", re.compile(r"localcities", re.I)),
    ("i-web", re.compile(r"i-web\.ch", re.I)),
    ("Zurich AS (bespoke)", re.compile(r'"ASZ"|amtliche-sammlung', re.I)),
)
ELI_RE = re.compile(r"property\s*=\s*[\"']eli:|vocab=[\"'][^\"']*eli", re.I)
JSONLD_RE = re.compile(r'<script[^>]+type=["\']application/ld\+json["\']', re.I)
GENERATOR_RE = re.compile(
    r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']([^"\']+)', re.I
)
PDF_LINK_RE = re.compile(r'href=["\'][^"\']+\.pdf', re.I)
DOC_LINK_RE = re.compile(
    r'href=["\'][^"\']*(texts_of_law|erlass|reglement|/\d+\.\d+)', re.I
)


@dataclass
class PortalRow:
    """One commune's row in the survey table."""

    bfs_id: int
    name: str
    canton: str
    language: str
    # Phase A
    vendor_subdomain: str | None = None
    candidate_domains: list[str] = field(default_factory=list)
    domain_source: str = "none"  # wikidata | dns-guess | none
    # Phase B2 — sitemap
    sitemap_url: str | None = None
    sitemap_entries: int = 0
    # True only when `sitemap_entries` counts the WHOLE site. A sitemap index is
    # followed one child deep (cheap signal, not a crawl), so its count is a
    # fragment. Absence may only be claimed from a complete enumeration -- see
    # the `no_collection_published` guard in `fingerprint`.
    sitemap_complete: bool = False
    # Phase B
    collection_url: str | None = None
    http_status: int | None = None
    platform: str | None = None
    generator: str | None = None
    has_eli: bool = False
    has_jsonld: bool = False
    pdf_links: int = 0
    doc_links: int = 0
    # Phase C
    classified_by: str = "none"  # none | fingerprint | llm
    structure: str | None = None
    manifestation: str | None = None
    llm_evidence: str | None = None
    confidence: float | None = None
    # Always
    # vendor_hit | fingerprinted | classified | ambiguous | undiscovered |
    # no_collection_published | not_probed | error
    outcome: str = "not_probed"
    note: str | None = None


# ── Phase A: discovery (DNS only) ──────────────────────────────────────────


def strip_accents(value: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", value) if not unicodedata.combining(c)
    )


def name_forms(name: str) -> list[str]:
    """Distinct readings of a commune name, before any hostname munging.

    A Swiss commune name is not always one name. Three shapes need splitting apart,
    and the previous version dropped all three on the floor because the final
    hostname-safety filter discarded any variant containing a stray character rather
    than cleaning it:

      `Buchs (AG)`   -> `buchs`, `buchs-ag`   (parenthesised canton disambiguator)
      `Biel/Bienne`  -> `biel`, `bienne`, `biel-bienne`   (bilingual double name)
      `Wohlen bei Bern` -> `wohlen-bei-bern`, `wohlen-bern`, `wohlen`

    83 communes were parenthesised and 54 were slashed or `bei`-qualified; all 137
    produced zero candidate domains and were recorded as `undiscovered` without a
    single request ever being made for them.
    """
    base = name.strip().lower()
    forms: list[str] = []

    paren = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", base)
    if paren:
        stem, qualifier = paren.group(1).strip(), paren.group(2).strip()
        forms.extend([stem, f"{stem} {qualifier}"])
        base = stem
    else:
        forms.append(base)

    for form in list(forms):
        if "/" in form:
            halves = [h.strip() for h in form.split("/") if h.strip()]
            forms.extend(halves)
            forms.append(" ".join(halves))
        # `bei` / `b.` / `près de` qualify a name; the bare stem and the compacted
        # form are both observed as domains (`wohlen-bern.ch`, `wohlen.ch`).
        qualified = re.match(
            r"^(.*?)\s+(?:bei|b\.|pres de|près de|presso)\s+(.*)$", form
        )
        if qualified:
            stem, place = qualified.group(1).strip(), qualified.group(2).strip()
            forms.extend([stem, f"{stem} {place}"])

    return [f for f in dict.fromkeys(forms) if f]


def slug_variants(name: str, canton: str) -> list[str]:
    """Hostname-safe slug candidates for a commune name.

    Derived from observed LexWork tenants: `winterthur`, `st.gallen` (space dropped,
    dot kept), `reinach-bl` (canton-suffixed), `oberaegeri` (umlaut transliterated).

    Characters that cannot appear in a hostname are now stripped rather than used to
    reject the whole variant — see `name_forms` for why that distinction cost 137 rows.
    """
    out: set[str] = set()
    for form in name_forms(name):
        umlaut = form.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
        for variant in {form, umlaut, strip_accents(form)}:
            for spaced in (variant.replace(" ", ""), variant.replace(" ", "-")):
                # Drop anything still not hostname-legal instead of discarding `spaced`.
                cleaned = "".join(ch for ch in spaced if ch.isalnum() or ch in ".-")
                cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-.")
                if not cleaned:
                    continue
                out.add(cleaned)
                # `Buchs (AG)` already carries its canton; re-suffixing yields
                # `buchs-ag-ag`, which resolves nowhere and only costs a lookup.
                if canton and not cleaned.endswith(f"-{canton}"):
                    out.add(f"{cleaned}-{canton}")
    return sorted(out)


# Wikidata carries an official website (P856) for essentially every Swiss commune,
# keyed by the same BFS number the overlay uses (P771). One free query replaces the
# slug guessing for the hard tail: `Buchs (AG)` is `buchs-aargau.ch`,
# `Rudolfstetten-Friedlisberg` is `rudolfstetten.ch`, `Hausen (AG)` is `hausen.swiss`
# — 196 communes whose real host no slug rule was ever going to produce, plus the 22
# on a TLD other than `.ch`, which `own_hosts` cannot express at all.
#
# It is a supplement, not a replacement: DNS guessing still runs, because Wikidata is
# community-maintained and a stale URL there must not silently become the only
# candidate. The official host is simply tried first.
WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"
WIKIDATA_QUERY = (
    "SELECT ?bfs ?website WHERE { "
    "?m wdt:P31/wdt:P279* wd:Q70208 ; wdt:P771 ?bfs ; wdt:P856 ?website . }"
)
DOMAIN_CACHE_FILE = "wikidata-official-domains.json"


def load_official_domains(cache_dir: Path, refresh: bool = False) -> dict[str, str]:
    """BFS number -> official website host, from Wikidata, cached on disk.

    Cached because it is reference data, not a probe: re-querying WDQS on every run
    would be rude for a result that changes a handful of times a year. A failed query
    is not fatal — the survey falls back to DNS guessing and says so per row, rather
    than pretending the tail is undiscoverable.
    """
    cache = cache_dir / DOMAIN_CACHE_FILE
    if cache.exists() and not refresh:
        return json.loads(cache.read_text(encoding="utf-8"))

    import httpx

    response = httpx.post(
        WIKIDATA_ENDPOINT,
        data={"query": WIKIDATA_QUERY},
        headers={"User-Agent": USER_AGENT, "Accept": "application/sparql-results+json"},
        timeout=180,
        follow_redirects=True,
    )
    response.raise_for_status()
    domains: dict[str, str] = {}
    for binding in response.json()["results"]["bindings"]:
        host = urlsplit(binding["website"]["value"]).netloc.lower()
        if host:
            domains[binding["bfs"]["value"]] = host
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(domains, indent=1, sort_keys=True), encoding="utf-8")
    return domains


def resolves(host: str) -> bool:
    try:
        socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
        return True
    except (socket.gaierror, UnicodeError, OSError):
        return False


# Nonsense labels used to detect wildcard DNS. If these resolve under a vendor's
# suffix, every lookup under it returns True and the probe proves nothing.
_WILDCARD_PROBES = ("zzz-nonexistent-test", "definitely-not-real-xyz9")


@lru_cache(maxsize=None)
def vendor_dns_is_usable(suffix: str) -> bool:
    """Can DNS distinguish a real tenant from a nonexistent one under `suffix`?

    `lexwork.naz.ch` wildcards: every label resolves, so a DNS hit there is not
    evidence of anything. Discovered by probe rather than by assumption after the
    first pilot reported 58% of communes on that vendor — a discovery method that
    can only answer yes is worth exactly nothing, and reads as a finding.
    """
    return not any(resolves(probe + suffix) for probe in _WILDCARD_PROBES)


def discover(
    row: PortalRow, official_domains: dict[str, str] | None = None, workers: int = 32
) -> PortalRow:
    """Phase A — find a vendor tenant or a plausible commune domain. DNS only."""
    slugs = slug_variants(row.name, row.canton)
    official = (official_domains or {}).get(str(row.bfs_id))
    # Only vendors whose DNS can actually say "no" are probed this way; the rest
    # must be confirmed over HTTP in phase B or not at all.
    usable = {
        v: s for v, s in VENDOR_SUBDOMAIN_SUFFIXES.items() if vendor_dns_is_usable(s)
    }
    vendor_hosts = [
        (vendor, slug + suffix) for slug in slugs for vendor, suffix in usable.items()
    ]
    own_hosts = [
        f"{prefix}{slug}.ch" for slug in slugs for prefix in ("www.", "", "gemeinde-")
    ]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        vendor_ok = list(pool.map(lambda vh: resolves(vh[1]), vendor_hosts))
        own_ok = list(pool.map(resolves, own_hosts))

    for (vendor, host), ok in zip(vendor_hosts, vendor_ok):
        if ok:
            row.vendor_subdomain = host
            row.platform = vendor
            row.outcome = "vendor_hit"
            break
    skipped = [
        v for v, s in VENDOR_SUBDOMAIN_SUFFIXES.items() if not vendor_dns_is_usable(s)
    ]
    if skipped:
        # Recorded per row so the table never implies coverage the method cannot give.
        row.note = (
            f"DNS discovery unusable (wildcard) for: {', '.join(sorted(skipped))}"
        )

    guessed = [h for h, ok in zip(own_hosts, own_ok) if ok]
    # The official host leads and is not subject to the DNS filter above: if Wikidata
    # names it, it is a better candidate than anything a slug rule produced, and a
    # host that fails to resolve simply 404s cheaply in phase B.
    ordered = ([official] if official else []) + [h for h in guessed if h != official]
    row.candidate_domains = ordered[:3]
    row.domain_source = "wikidata" if official else ("dns-guess" if guessed else "none")
    return row


# ── Phase B: fingerprint (one polite GET per candidate) ────────────────────


class PoliteFetcher:
    """One request at a time per host, robots.txt honoured, responses cached."""

    def __init__(self, cache_dir: Path, delay: float = REQUEST_DELAY_SECONDS) -> None:
        import httpx

        self._client = httpx.Client(
            follow_redirects=True,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
        )
        self._delay = delay
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._robots: dict[str, RobotFileParser | None] = {}
        # Per-HOST, not global. A global clock is not politer — it is the same load
        # on each site, spread over 26 hours instead of 2. What a site experiences is
        # requests to *it*, so the delay belongs per origin, and different communes
        # can then be probed concurrently.
        self._last_request: dict[str, float] = {}
        self._lock = threading.Lock()

    def _allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            parser = RobotFileParser()
            parser.set_url(f"{origin}/robots.txt")
            try:
                parser.read()
            except Exception:
                parser = None  # No robots.txt reachable: default to allowed.
            self._robots[origin] = parser
        parser = self._robots[origin]
        return True if parser is None else parser.can_fetch(USER_AGENT, url)

    def get(self, url: str) -> tuple[int | None, str]:
        key = self._cache_dir / (
            re.sub(r"[^a-z0-9]+", "_", url.lower())[:150] + ".html"
        )
        if key.exists():
            return 200, key.read_text(encoding="utf-8", errors="replace")
        if not self._allowed(url):
            return None, ""
        host = urlsplit(url).netloc
        with self._lock:
            elapsed = time.monotonic() - self._last_request.get(host, 0.0)
            if elapsed < self._delay:
                time.sleep(self._delay - elapsed)
            self._last_request[host] = time.monotonic()
        try:
            response = self._client.get(url)
        except Exception:
            return None, ""
        body = response.text[:400_000]
        if response.status_code == 200:
            key.write_text(body, encoding="utf-8")
        return response.status_code, body


def probe_urls(row: PortalRow) -> list[str]:
    """URLs to probe for one commune, most likely first.

    Ordered breadth-first BY PATH, not depth-first by domain. The distinction is the
    whole fix: the previous order emitted domain 1 x every path before domain 2's
    first, so a truncating budget of 8 spent every probe on one domain and never
    reached the others — 765 communes had a second resolved domain that was never
    requested. Path rank matters more than domain rank, so path rank varies slowest.
    """
    candidates: list[str] = []
    if row.vendor_subdomain:
        candidates.append(f"https://{row.vendor_subdomain}/app/de/overview")
        candidates.append(f"https://{row.vendor_subdomain}/app/")
    for path in collection_paths(row.language):
        candidates.extend(f"https://{domain}{path}" for domain in row.candidate_domains)
    return list(dict.fromkeys(candidates))


# Words a Swiss commune uses for its legal collection, in the four languages a site
# might publish in. Matched against sitemap URLs, so it is deliberately generous —
# a false positive costs one HTTP probe that then fails to fingerprint, whereas a
# false negative is recorded as "publishes nothing", which is a much worse error.
COLLECTION_VOCAB = re.compile(
    r"rechtssammlung|erlasssammlung|erlass-sammlung|erlasse|gesetzessammlung"
    r"|reglement|satzung"
    r"|recueil|r[eè]glement|l[eé]gislation"
    r"|regolament|raccolta|ordinanz",
    re.I,
)
# A sitemap smaller than this is a stub (a homepage-only or index-only file) and
# cannot support a claim about what the site does not contain.
MIN_SITEMAP_FOR_ABSENCE = 20


def sitemap_candidates(row: PortalRow, fetcher: PoliteFetcher) -> tuple[list[str], int]:
    """Collection URLs found in the site's own sitemap, and the sitemap's size.

    Two requests at most, and worth far more than the ~70 a depth-2 crawl would cost:
    a sitemap enumerates the whole site at once. Niederwil's nav has no collection
    link anywhere in 72 links, so crawling would have missed it regardless.

    The size is returned because it is what licenses the `no_collection_published`
    outcome. A complete sitemap with no collection vocabulary in it is evidence of
    absence; a 404 or a stub is merely absence of evidence, and the two must not be
    recorded the same way.
    """
    if not row.candidate_domains:
        return [], 0
    host = row.candidate_domains[0]

    locations: list[str] = []
    declared_total = 1
    status, body = fetcher.get(f"https://{host}/sitemap.xml")
    if status == 200 and body:
        row.sitemap_url = f"https://{host}/sitemap.xml"
    else:
        # robots.txt names the sitemap when it is not at the conventional path.
        #
        # It may name MANY. Large CMS-driven municipal sites partition their
        # sitemap per section, and `re.search` takes whichever happens to be
        # first — which is how Stadt Zürich was recorded as publishing no law:
        # its robots.txt declares a dozen section sitemaps, the first is the
        # Friedhofforum (cemetery forum), and its 27 pages were read as the whole
        # city. Take them all, and remember how many were reachable, because
        # absence may only be claimed over a set that was actually enumerated.
        status, robots = fetcher.get(f"https://{host}/robots.txt")
        declared_urls = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", robots or "")
        if not declared_urls:
            return [], 0
        declared_total = len(declared_urls)
        fetched = 0
        for declared_url in declared_urls[:MAX_DECLARED_SITEMAPS]:
            status, part = fetcher.get(declared_url)
            if status != 200 or not part:
                continue
            fetched += 1
            if row.sitemap_url is None:
                row.sitemap_url = declared_url
            locations.extend(re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", part))
        if not fetched:
            return [], 0
        # Complete only if every declared sitemap was reached.
        row.sitemap_complete = fetched == declared_total
        return [u for u in locations if COLLECTION_VOCAB.search(u)], len(locations)

    locations = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", body)
    # A sitemap index points at further sitemaps rather than pages. Follow only the
    # first, and only one level: the goal is a cheap signal, not a crawl.
    #
    # That bound is fine for FINDING a collection and fatal for claiming its ABSENCE:
    # what comes back is one arbitrary child sitemap, not the site. Stadt Zürich's
    # index led with the Friedhofforum sitemap, so the survey read 27 cemetery pages
    # as the whole city and reported the Amtliche Sammlung as unpublished. Mark the
    # count as a fragment so `fingerprint` refuses to conclude absence from it.
    is_index = "<sitemapindex" in body.lower()
    if is_index and locations:
        status, nested = fetcher.get(locations[0])
        if status == 200 and nested:
            locations = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", nested)
    row.sitemap_complete = not is_index

    return [u for u in locations if COLLECTION_VOCAB.search(u)], len(locations)


# How many sitemap-derived candidates to actually fetch. The vocabulary match is
# generous by design, so this bounds what that generosity can cost.
SITEMAP_PROBE_LIMIT = 3

# robots.txt may declare a sitemap per site section. Bounded so one sprawling
# municipal site cannot dominate the survey's request budget; when the bound
# truncates, `sitemap_complete` stays False and absence is not claimable.
MAX_DECLARED_SITEMAPS = 12


def analyze_page(row: PortalRow, url: str, status: int, body: str) -> bool:
    """Record what a fetched page is. Returns True if the row is settled.

    Shared by the guessed-path probe and the sitemap probe so that a collection found
    via the sitemap is held to exactly the same evidence bar as one found by guessing.
    """
    row.collection_url = url
    row.http_status = status
    for label, pattern in VENDOR_MARKERS:
        if pattern.search(body):
            row.platform = label
            break
    generator = GENERATOR_RE.search(body)
    row.generator = generator.group(1)[:80] if generator else None
    row.has_eli = bool(ELI_RE.search(body))
    row.has_jsonld = bool(JSONLD_RE.search(body))
    row.pdf_links = len(PDF_LINK_RE.findall(body))
    row.doc_links = len(DOC_LINK_RE.findall(body))
    if row.platform or row.doc_links >= 5:
        row.classified_by = "fingerprint"
        row.outcome = "fingerprinted"
        row.manifestation = "pdf" if row.pdf_links > row.doc_links else "html"
        row.structure = f"{row.doc_links} document links"
        return True
    row.outcome = "ambiguous"
    return True


def fingerprint(row: PortalRow, fetcher: PoliteFetcher) -> PortalRow:
    """Phase B — deterministic classification. No model, no opinion."""
    candidates = probe_urls(row)

    if not candidates:
        # Nothing resolved in phase A, so no request is possible. This is NOT the same
        # as having looked and found nothing, and conflating the two is what let the
        # survey report 919 `undiscovered` when 137 of them were never contacted.
        row.outcome = "not_probed"
        row.note = "phase A resolved no vendor tenant and no candidate domain"
        return row

    # Bounded: a commune whose collection is not on any of these falls through to the
    # sitemap probe, which is cheaper than probing 30 dead URLs here.
    for url in candidates[:MAX_HTTP_ATTEMPTS]:
        status, body = fetcher.get(url)
        if status == 200 and body and analyze_page(row, url, status, body):
            return row

    # Nothing at a guessed path. Ask the site to enumerate itself rather than guessing
    # harder — and let a complete answer of "no such page" be a finding in its own right.
    hits, entries = sitemap_candidates(row, fetcher)
    row.sitemap_entries = entries
    for url in hits[:SITEMAP_PROBE_LIMIT]:
        status, body = fetcher.get(url)
        if status == 200 and body and analyze_page(row, url, status, body):
            return row

    attempted = min(len(candidates), MAX_HTTP_ATTEMPTS)
    if entries >= MIN_SITEMAP_FOR_ABSENCE and not hits and row.sitemap_complete:
        # The site listed every page it has and none of them is a legal collection.
        # That answers "what would this commune cost to acquire?" with "it cannot be,
        # not by scraping" — which is a result, not a gap, and must not be re-probed
        # forever as though it were one.
        #
        # `sitemap_complete` is load-bearing, not defensive. Without it this branch
        # fired on one child of a sitemap index and asserted a fact about the whole
        # commune: all 183 absence claims in the first full survey were sitemap-derived,
        # and Zürich — the one commune with independent ground truth in
        # `communal_portals.yaml` ("Amtliche Sammlung (verified)") — was among them.
        # An unproven absence is worse than `undiscovered`: `undiscovered` admits
        # ignorance, this claims knowledge, and downstream it stops the row ever being
        # re-probed.
        row.outcome = "no_collection_published"
        row.note = (
            f"sitemap enumerates {entries} pages, none matching collection vocabulary "
            f"({row.sitemap_url})"
        )
        return row

    row.outcome = "undiscovered"
    # Record the budget actually spent. "Nothing found" is only meaningful next to how
    # hard the survey looked, and a truncated probe list reads identically to an
    # exhausted one unless the row says which it was.
    sitemap_note = (
        f"sitemap {entries} entries, {len(hits)} candidate(s)"
        f"{'' if row.sitemap_complete else ' (index — fragment only, absence not claimable)'}"
        if row.sitemap_url
        else "no sitemap"
    )
    row.note = (
        f"no candidate URL returned 200 ({attempted} of {len(candidates)} probed"
        f"{', budget-truncated' if len(candidates) > MAX_HTTP_ATTEMPTS else ''}; "
        f"{sitemap_note})"
    )
    return row


# ── Phase C: classify (LLM, last resort) ───────────────────────────────────

CLASSIFY_SYSTEM = """You classify Swiss municipal legal-collection web pages.

Answer ONLY from the page text supplied. For every field, quote the verbatim span
you relied on in `evidence`. If the page does not support a field, return null for
it — do NOT infer, and do NOT use general knowledge about the municipality. A
confident wrong answer is worse here than an absent one: this survey decides
engineering effort, and a fabricated 'yes, this is a legal collection' costs a
parser nobody needed."""


def classify(row: PortalRow, body: str, model: str) -> PortalRow:
    """Phase C — only for pages phase B left ambiguous."""
    try:
        import instructor
        from openai import OpenAI
        from pydantic import BaseModel, Field
    except ImportError:
        row.note = "classify requested but instructor/openai not installed"
        return row

    class Classification(BaseModel):
        is_legal_collection: bool | None = Field(
            description="Is this a systematic collection of municipal law? null if unclear."
        )
        platform: str | None = Field(
            description="CMS/vendor if named on the page, else null."
        )
        manifestation: str | None = Field(
            description="'pdf', 'html', 'mixed', or null."
        )
        evidence: str | None = Field(description="Verbatim span justifying the above.")
        confidence: float = Field(ge=0.0, le=1.0)

    text = re.sub(r"<[^>]+>", " ", body)
    text = re.sub(r"\s+", " ", text)[:6000]
    client = instructor.from_openai(OpenAI())
    try:
        result = client.chat.completions.create(
            model=model,
            response_model=Classification,
            messages=[
                {"role": "system", "content": CLASSIFY_SYSTEM},
                {
                    "role": "user",
                    "content": f"URL: {row.collection_url}\n\nPAGE TEXT:\n{text}",
                },
            ],
        )
    except Exception as exc:  # noqa: BLE001 - a survey row should not kill the run
        row.note = f"classify failed: {exc}"[:200]
        return row

    # An unevidenced classification is recorded as unknown, not accepted.
    if not result.evidence:
        row.note = "llm returned no evidence span; treated as unknown"
        return row
    row.classified_by = "llm"
    row.outcome = "classified"
    row.platform = row.platform or result.platform
    row.manifestation = result.manifestation
    row.llm_evidence = result.evidence[:300]
    row.confidence = result.confidence
    return row


# ── Driver ─────────────────────────────────────────────────────────────────


def load_communes() -> list[dict[str, Any]]:
    import yaml

    data = yaml.safe_load(MUNICIPALITIES.read_text(encoding="utf-8"))
    for value in data.values():
        if (
            isinstance(value, list)
            and value
            and isinstance(value[0], dict)
            and "bfs_id" in value[0]
        ):
            return value
    raise SystemExit("could not locate the municipality list in municipalities.yaml")


def load_done(checkpoint: Path) -> dict[int, dict[str, Any]]:
    if not checkpoint.exists():
        return {}
    done = {}
    for line in checkpoint.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            done[row["bfs_id"]] = row
    return done


def render_report(rows: list[dict[str, Any]]) -> str:
    total = len(rows)
    by_platform: dict[str, int] = {}
    by_outcome: dict[str, int] = {}
    for row in rows:
        by_platform[row.get("platform") or "unknown"] = (
            by_platform.get(row.get("platform") or "unknown", 0) + 1
        )
        by_outcome[row["outcome"]] = by_outcome.get(row["outcome"], 0) + 1

    lines = [
        f"# Communal portal survey — {total} communes probed",
        "",
        "## By platform",
        "",
    ]
    lines += ["| platform | communes | share |", "|---|---:|---:|"]
    for platform, count in sorted(by_platform.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {platform} | {count} | {100 * count / total:.1f}% |")
    lines += ["", "## By outcome", "", "| outcome | communes |", "|---|---:|"]
    for outcome, count in sorted(by_outcome.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {outcome} | {count} |")
    lines += [
        "",
        "## Rows",
        "",
        "| BFS | commune | canton | platform | URL | ELI | JSON-LD | manifestation | via |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in sorted(rows, key=lambda r: r["bfs_id"]):
        lines.append(
            f"| {row['bfs_id']} | {row['name']} | {row['canton']} | "
            f"{row.get('platform') or '—'} | {row.get('collection_url') or '—'} | "
            f"{'yes' if row.get('has_eli') else 'no'} | "
            f"{'yes' if row.get('has_jsonld') else 'no'} | "
            f"{row.get('manifestation') or '—'} | {row.get('classified_by')} |"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit", type=int, default=50, help="communes to probe (default 50)"
    )
    parser.add_argument("--all", action="store_true", help="probe every commune")
    parser.add_argument("--classify", action="store_true", help="enable the LLM phase")
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument(
        "--report", action="store_true", help="render from checkpoint, no network"
    )
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY_SECONDS)
    parser.add_argument("--workers", type=int, default=12, help="concurrent communes")
    parser.add_argument(
        "--reprobe",
        action="store_true",
        help=(
            "re-probe rows whose outcome carries no finding (undiscovered/not_probed/"
            "error). Use after a discovery fix: resume otherwise skips exactly the "
            "rows the fix was meant to reach. Confirmed hits are never re-probed."
        ),
    )
    parser.add_argument(
        "--refresh-domains",
        action="store_true",
        help="re-query Wikidata for official commune websites instead of using the cache",
    )
    args = parser.parse_args()

    done = load_done(args.checkpoint)

    if args.report:
        if not done:
            raise SystemExit(f"no checkpoint at {args.checkpoint}")
        print(render_report(list(done.values())))
        return 0

    communes = load_communes()
    # A row that found nothing is a row the next discovery fix is aimed at, so it does
    # not count as done under --reprobe. The checkpoint is append-only and load_done
    # keys by bfs_id with last-write-wins, so a fresh row simply supersedes the stale
    # one — no rewrite, and the old row stays on disk as history.
    # `no_collection_published` is deliberately NOT here: it is a positive finding
    # backed by the site's own sitemap, not a gap waiting for a better probe.
    barren = {"undiscovered", "not_probed", "error"}
    stale = {b for b, r in done.items() if args.reprobe and r.get("outcome") in barren}
    todo = [c for c in communes if c["bfs_id"] not in done or c["bfs_id"] in stale]
    if not args.all:
        todo = todo[: args.limit]
    print(
        f"{len(communes)} communes, {len(done)} already done"
        f"{f' ({len(stale)} being re-probed)' if stale else ''}, probing {len(todo)}",
        file=sys.stderr,
    )
    if args.all and len(todo) > 200:
        print(
            f"NOTE: about to contact up to {len(todo)} municipal sites at "
            f"{args.delay}s intervals — roughly {len(todo) * args.delay / 3600:.1f}h. "
            "Ctrl-C is safe; progress is checkpointed.",
            file=sys.stderr,
        )

    cache_dir = args.checkpoint.parent / ".portal-cache"
    fetcher = PoliteFetcher(cache_dir, delay=args.delay)
    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)

    try:
        official_domains = load_official_domains(
            cache_dir, refresh=args.refresh_domains
        )
        print(
            f"official websites from Wikidata: {len(official_domains)}", file=sys.stderr
        )
    except Exception as exc:  # noqa: BLE001 - the survey still works without them
        official_domains = {}
        print(
            f"WARNING: Wikidata lookup failed ({exc}); falling back to DNS slug "
            "guessing, which misses the ~196 communes whose host no rule produces.",
            file=sys.stderr,
        )

    def probe_one(commune: dict[str, Any]) -> PortalRow:
        row = PortalRow(
            bfs_id=commune["bfs_id"],
            name=commune.get("name", ""),
            canton=(commune.get("canton_jurisdiction_id") or "").rsplit("_", 1)[-1],
            language=commune.get("primary_language", ""),
        )
        try:
            discover(row, official_domains)
            fingerprint(row, fetcher)
            if args.classify and row.outcome == "ambiguous" and row.collection_url:
                _, body = fetcher.get(row.collection_url)
                if body:
                    classify(row, body, args.model)
        except Exception as exc:  # noqa: BLE001 - one bad row must not end the survey
            row.outcome = "error"
            row.note = str(exc)[:200]
        return row

    # Concurrency is across COMMUNES; the delay inside the fetcher is per HOST, so a
    # single site still sees one request every `--delay` seconds no matter how many
    # workers are running.
    write_lock = threading.Lock()
    completed = 0
    with args.checkpoint.open("a", encoding="utf-8") as sink:
        try:
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                for row in pool.map(probe_one, todo):
                    with write_lock:
                        sink.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")
                        sink.flush()
                    completed += 1
                    print(
                        f"[{completed}/{len(todo)}] {row.bfs_id} {row.name}: "
                        f"{row.outcome} platform={row.platform}",
                        file=sys.stderr,
                    )
        except KeyboardInterrupt:
            print(
                "\ninterrupted — checkpoint is intact, re-run to resume",
                file=sys.stderr,
            )

    print(render_report(list(load_done(args.checkpoint).values())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
