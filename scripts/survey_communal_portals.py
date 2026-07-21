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

  A. discover  — DNS only. Known vendor subdomains + candidate commune domains.
                 No HTTP, no cost, no load on anyone.
  B. fingerprint — one polite HTTP GET per candidate. Vendor markers, `generator`
                 meta, JSON-LD / RDFa / ELI, link shapes (PDF vs HTML).
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

USAGE
-----
    # pilot, no API key needed — phases A+B only
    uv run --with pyyaml,httpx python scripts/survey_communal_portals.py --limit 50

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
DEFAULT_CHECKPOINT = REPO_ROOT / "docs" / "runbooks" / "evidence" / "communal-portal-survey.jsonl"

USER_AGENT = (
    "EvidaraPortalSurvey/1.0 (+https://github.com/philipplukas/evidara; "
    "legal-corpus coverage research; contact via repository issues)"
)
REQUEST_DELAY_SECONDS = 1.5
# Cap on HTTP probes per commune before giving up and deferring to the agent pass.
MAX_HTTP_ATTEMPTS = 8
REQUEST_TIMEOUT_SECONDS = 8

# Vendors that host communes as per-tenant subdomains. Confirmed for tlex on
# 2026-07-21 (43 tenants, no wildcard DNS). The others are candidates to test —
# an empty result for one of them is itself a finding worth recording.
VENDOR_SUBDOMAIN_SUFFIXES = {
    "tlex": ".tlex.ch",
    "lexwork_naz": ".lexwork.naz.ch",
    "weblaw": ".weblaw.ch",
}

# Paths a Swiss commune commonly publishes its collection under. Ordered by how
# often they appeared in manual inspection; the first 200 wins.
COLLECTION_PATHS = (
    "/rechtssammlung",
    "/erlasssammlung",
    "/erlass-sammlung",
    "/gesetzessammlung",
    "/reglemente",
    "/themen/die-stadt/erlass-sammlung",
    "/politik/reglemente",
    "/verwaltung/reglemente",
    "/recueil-systematique",
    "/reglements",
)

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
GENERATOR_RE = re.compile(r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']([^"\']+)', re.I)
PDF_LINK_RE = re.compile(r'href=["\'][^"\']+\.pdf', re.I)
DOC_LINK_RE = re.compile(r'href=["\'][^"\']*(texts_of_law|erlass|reglement|/\d+\.\d+)', re.I)


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
    outcome: str = "not_probed"  # vendor_hit | fingerprinted | classified | undiscovered | error
    note: str | None = None


# ── Phase A: discovery (DNS only) ──────────────────────────────────────────


def strip_accents(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", value) if not unicodedata.combining(c))


def slug_variants(name: str, canton: str) -> list[str]:
    """Hostname-safe slug candidates for a commune name.

    Derived from observed LexWork tenants: `winterthur`, `st.gallen` (space dropped,
    dot kept), `reinach-bl` (canton-suffixed), `oberaegeri` (umlaut transliterated).
    """
    base = name.strip().lower()
    umlaut = base.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    plain = strip_accents(base)
    out: set[str] = set()
    for variant in {base, umlaut, plain}:
        for spaced in (variant.replace(" ", ""), variant.replace(" ", "-")):
            out.add(spaced)
            if canton:
                out.add(f"{spaced}-{canton}")
    return sorted(c for c in out if c and all(ch.isalnum() or ch in ".-" for ch in c))


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


def discover(row: PortalRow, workers: int = 32) -> PortalRow:
    """Phase A — find a vendor tenant or a plausible commune domain. DNS only."""
    slugs = slug_variants(row.name, row.canton)
    # Only vendors whose DNS can actually say "no" are probed this way; the rest
    # must be confirmed over HTTP in phase B or not at all.
    usable = {v: s for v, s in VENDOR_SUBDOMAIN_SUFFIXES.items() if vendor_dns_is_usable(s)}
    vendor_hosts = [(vendor, slug + suffix) for slug in slugs for vendor, suffix in usable.items()]
    own_hosts = [f"{prefix}{slug}.ch" for slug in slugs for prefix in ("www.", "", "gemeinde-")]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        vendor_ok = list(pool.map(lambda vh: resolves(vh[1]), vendor_hosts))
        own_ok = list(pool.map(resolves, own_hosts))

    for (vendor, host), ok in zip(vendor_hosts, vendor_ok):
        if ok:
            row.vendor_subdomain = host
            row.platform = vendor
            row.outcome = "vendor_hit"
            break
    skipped = [v for v, s in VENDOR_SUBDOMAIN_SUFFIXES.items() if not vendor_dns_is_usable(s)]
    if skipped:
        # Recorded per row so the table never implies coverage the method cannot give.
        row.note = f"DNS discovery unusable (wildcard) for: {', '.join(sorted(skipped))}"

    row.candidate_domains = [h for h, ok in zip(own_hosts, own_ok) if ok][:3]
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
        key = self._cache_dir / (re.sub(r"[^a-z0-9]+", "_", url.lower())[:150] + ".html")
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


def fingerprint(row: PortalRow, fetcher: PoliteFetcher) -> PortalRow:
    """Phase B — deterministic classification. No model, no opinion."""
    candidates: list[str] = []
    if row.vendor_subdomain:
        candidates.append(f"https://{row.vendor_subdomain}/app/de/overview")
        candidates.append(f"https://{row.vendor_subdomain}/app/")
    for domain in row.candidate_domains:
        candidates.extend(f"https://{domain}{path}" for path in COLLECTION_PATHS)

    # Bounded: a commune whose collection is not on any of these is `undiscovered`
    # and goes to the agent pass, which is cheaper than probing 30 dead URLs here.
    for url in candidates[:MAX_HTTP_ATTEMPTS]:
        status, body = fetcher.get(url)
        if status != 200 or not body:
            continue
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
            return row
        row.outcome = "ambiguous"
        return row

    row.outcome = "undiscovered"
    row.note = "no candidate URL returned 200"
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
        platform: str | None = Field(description="CMS/vendor if named on the page, else null.")
        manifestation: str | None = Field(description="'pdf', 'html', 'mixed', or null.")
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
                {"role": "user", "content": f"URL: {row.collection_url}\n\nPAGE TEXT:\n{text}"},
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
        if isinstance(value, list) and value and isinstance(value[0], dict) and "bfs_id" in value[0]:
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

    lines = [f"# Communal portal survey — {total} communes probed", "", "## By platform", ""]
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
    parser.add_argument("--limit", type=int, default=50, help="communes to probe (default 50)")
    parser.add_argument("--all", action="store_true", help="probe every commune")
    parser.add_argument("--classify", action="store_true", help="enable the LLM phase")
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--report", action="store_true", help="render from checkpoint, no network")
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY_SECONDS)
    parser.add_argument("--workers", type=int, default=12, help="concurrent communes")
    args = parser.parse_args()

    done = load_done(args.checkpoint)

    if args.report:
        if not done:
            raise SystemExit(f"no checkpoint at {args.checkpoint}")
        print(render_report(list(done.values())))
        return 0

    communes = load_communes()
    todo = [c for c in communes if c["bfs_id"] not in done]
    if not args.all:
        todo = todo[: args.limit]
    print(
        f"{len(communes)} communes, {len(done)} already done, probing {len(todo)}",
        file=sys.stderr,
    )
    if args.all and len(todo) > 200:
        print(
            f"NOTE: about to contact up to {len(todo)} municipal sites at "
            f"{args.delay}s intervals — roughly {len(todo) * args.delay / 3600:.1f}h. "
            "Ctrl-C is safe; progress is checkpointed.",
            file=sys.stderr,
        )

    fetcher = PoliteFetcher(args.checkpoint.parent / ".portal-cache", delay=args.delay)
    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)

    def probe_one(commune: dict[str, Any]) -> PortalRow:
        row = PortalRow(
            bfs_id=commune["bfs_id"],
            name=commune.get("name", ""),
            canton=(commune.get("canton_jurisdiction_id") or "").rsplit("_", 1)[-1],
            language=commune.get("primary_language", ""),
        )
        try:
            discover(row)
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
            print("\ninterrupted — checkpoint is intact, re-run to resume", file=sys.stderr)

    print(render_report(list(load_done(args.checkpoint).values())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
