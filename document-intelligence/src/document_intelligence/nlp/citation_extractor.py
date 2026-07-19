"""Legal citation extraction for Swiss, Austrian, EU, DE, FR, and IT legal documents.

Extracts references to:
- Swiss federal law (SR numbers): e.g., "SR 210", "SR 311.0"
- Swiss BGE decisions: e.g., "BGE 147 III 49", "BGE 148 IV 234"
- Austrian Federal Law Gazette: e.g., "BGBl. Nr. 43/1975", "BGBl. III Nr. 62/2013"
- EU regulations/directives: e.g., "Regulation (EU) 2016/679", "Directive 2013/36/EU"
- EU CELEX IDs: e.g., "32016R0679" (GDPR), "32019L0790" (Copyright Directive)
- EU ECLI identifiers: e.g., "ECLI:EU:C:2019:218", "ECLI:EU:T:2020:338"
- DE constitutional decisions: e.g., "BVerfGE 123, 45", "1 BvR 1234/56"
- DE supreme court decisions: e.g., "BGHZ 145, 12", "BGHSt 50, 100"
- FR Code articles: e.g., "Art. 1240 du Code civil", "Art. 121-3 du Code pénal"
- FR jurisprudence: e.g., "Cass. civ. 1re, 12 mars 2020, n° 18-12.345"
- IT Codice articles: e.g., "art. 2043 c.c.", "art. 575 c.p."
- IT Cassazione decisions: e.g., "Cass. civ. n. 1234/2020", "Cass. pen., sez. III, n. 5678/2019"
- Article references: e.g., "Art. 8 EMRK", "Art. 261bis StGB"
- Named statute abbreviations: e.g., "OR", "ZGB", "StGB", "SchKG"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Citation:
    """A single extracted legal citation."""

    text: str
    citation_type: str  # sr, bge, eu_regulation, eu_directive, article, statute
    start: int = 0
    end: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "citation_type": self.citation_type,
            "start": self.start,
            "end": self.end,
            **self.metadata,
        }


# Swiss SR numbers: "SR 210", "SR 311.0", "SR 220"
_SR_PATTERN = re.compile(
    r"\bSR\s+(\d{3}(?:\.\d+)*)\b",
)

# BGE decisions: "BGE 147 III 49", "BGE 148 IV 234 E. 3.2"
_BGE_PATTERN = re.compile(
    r"\bBGE\s+\d{1,3}\s+[IV]+\s+\d+(?:\s+E\.\s+[\d.]+)?\b",
)

# Austrian Federal Law Gazette:
# "BGBl. Nr. 43/1975", "BGBl. III Nr. 62/2013",
# and long-form "Bundesgesetzblatt Nr. 825 aus 1994".
_AT_BGBL_PATTERN = re.compile(
    r"\b(?:"
    r"BGBl\.\s*(?:(?P<part>[IVX]+)\s*)?Nr\.\s*(?P<number>\d+[a-zA-Z]?)/(?P<year>\d{4})"
    r"|Bundesgesetzblatt\s+(?:(?:Teil\s*)?(?P<part_word>[IVX]+)\s*,?\s*)?"
    r"Nr\.\s*(?P<number_word>\d+[a-zA-Z]?)\s+aus\s+(?P<year_word>\d{4})"
    r")\b",
    re.IGNORECASE,
)

# EU Regulations: "Regulation (EU) 2016/679", "Verordnung (EU) 2016/679"
_EU_REGULATION_PATTERN = re.compile(
    r"\b(?:Regulation|Verordnung|Règlement)\s*\((?:EU|EG|EC|CE)\)\s*(?:No\.?\s*)?\d{1,4}/\d{2,4}\b",
    re.IGNORECASE,
)

# EU Directives: "Directive 2013/36/EU", "Richtlinie 2014/65/EU"
_EU_DIRECTIVE_PATTERN = re.compile(
    r"\b(?:Directive|Richtlinie|Directive)\s*\d{4}/\d{1,4}/(?:EU|EG|EC|CE)\b",
    re.IGNORECASE,
)

# CELEX identifiers: 1-digit sector + 4-digit year + 1-or-2-letter descriptor +
# 4-digit doc number. Sector 3 (legislation) uses single letters (R regulation,
# L directive, D decision, E CFSP, H recommendation, C other). Sector 6 (case
# law) uses two-letter codes (CJ Court of Justice, TJ General Court, FJ Civil
# Service Tribunal). Example: "32016R0679" = GDPR; "62019CJ0311" = CJEU case.
_CELEX_PATTERN = re.compile(
    r"\b(?P<sector>[1-9])"
    r"(?P<year>\d{4})"
    r"(?P<descriptor>[A-Z]{1,2})"
    r"(?P<doc>\d{4})"
    r"(?:\([A-Z0-9]+\))?\b",
)

# ECLI identifiers for EU courts:
#   ECLI:EU:C:YYYY:NNN  → Court of Justice
#   ECLI:EU:T:YYYY:NNN  → General Court
#   ECLI:EU:F:YYYY:NNN  → Civil Service Tribunal (retired 2016)
# Year has 4 digits; ordinal is 1–5 digits (2024 growth-proof).
_ECLI_EU_PATTERN = re.compile(
    r"\bECLI:EU:(?P<court>[CTF]):(?P<year>\d{4}):(?P<ordinal>\d{1,5})\b",
)

# ─── Germany ──────────────────────────────────────────────────────────────

# BVerfGE (Bundesverfassungsgericht) volume + page citation:
# "BVerfGE 123, 45" or "BVerfGE 123, 45 (67)" where (67) is the page.
# No trailing \b — `)` is non-word, so \b after it would fail when followed
# by whitespace and prevent the optional pincite group from matching.
_DE_BVERFGE_PATTERN = re.compile(
    r"\bBVerfGE\s+\d{1,3},\s*\d{1,4}(?:\s*\(\d{1,4}\))?",
)

# BVerfG docket number: "1 BvR 1234/56" — senate / type / ordinal / year.
# Senate is 1 or 2; type is letters (BvR, BvL, BvE, BvF, BvG, BvK, BvM, BvN, BvQ, PBvU).
_DE_BVERFG_DOCKET_PATTERN = re.compile(
    r"\b(?P<senate>[12])\s+(?P<type>BvR|BvL|BvE|BvF|BvG|BvK|BvM|BvN|BvQ|PBvU)\s+(?P<ordinal>\d{1,5})/(?P<year>\d{2,4})\b",
)

# BGH volume + page: "BGHZ 145, 12" (civil) / "BGHSt 50, 100" (criminal).
_DE_BGH_PATTERN = re.compile(
    r"\b(?P<reporter>BGHZ|BGHSt)\s+\d{1,3},\s*\d{1,4}(?:\s*\(\d{1,4}\))?\b",
)

# ECLI:DE: national ECLI scheme. "ECLI:DE:BVERFG:2020:rs20200120.1bvr164519"
# is a real example; ordinal portion is free-form so we match loosely.
_DE_ECLI_PATTERN = re.compile(
    r"\bECLI:DE:(?P<court>[A-Z]{2,10}):(?P<year>\d{4}):(?P<ordinal>[A-Za-z0-9._-]+)\b",
)

# German § (paragraph) with named statute: "§ 823 BGB", "§§ 242, 243 StGB".
# Matches a single § with one or more comma-separated numbers and a curated
# list of common German statute abbreviations. Curated list is more reliable
# than a suffix-anchored pattern because the {1,8} greedy quantifier would
# otherwise eat the required suffix letters.
_DE_PARAGRAPH_PATTERN = re.compile(
    r"§§?\s*\d+[a-z]?(?:\s*,\s*\d+[a-z]?)*\s+"
    r"(?P<statute>"
    r"BGB|StGB|ZPO|StPO|HGB|GG|AO|AktG|UWG|UrhG|MarkenG|PatG|"
    r"InsO|EStG|KStG|UStG|GewO|BauGB|BauNVO|SGB|VwVfG|VwGO|"
    r"GVG|MietspiegelG|TKG|TMG|BDSG|BetrVG|KSchG|ArbGG|StVO|StVG"
    r")\b",
)

# ─── France ───────────────────────────────────────────────────────────────

# Code article: "Art. 1240 du Code civil" / "article L. 121-3 du Code pénal"
# / "Art. R. 611-1 du Code de commerce". Supports L./R./D. prefixes and
# hyphenated subpart numbers.
_FR_CODE_ARTICLE_PATTERN = re.compile(
    r"\b(?:[Aa]rt(?:icle)?\.?)\s+(?:[LRD]\.?\s*)?\d+(?:-\d+)*\s+du\s+[Cc]ode\s+(?:civil|p[ée]nal|de\s+(?:commerce|proc[ée]dure\s+(?:civile|p[ée]nale))|du\s+travail|de\s+l['’]environnement|de\s+la\s+consommation|de\s+la\s+sant[ée]\s+publique|des\s+assurances)\b",
)

# Pourvoi (Cour de cassation docket): "n° 18-12.345" / "pourvoi n° 20-10.123".
_FR_POURVOI_PATTERN = re.compile(
    r"\b(?:pourvoi\s+)?n[°º]\s*(?P<num>\d{2}-\d{2}\.\d{3,5})\b",
    re.IGNORECASE,
)

# Cour de cassation chamber + date + pourvoi, compact form:
# "Cass. civ. 1re, 12 mars 2020, n° 18-12.345" — we match the prefix shape
# without requiring the date to stay permissive.
_FR_CASS_PATTERN = re.compile(
    r"\bCass\.?\s*(?:civ|com|soc|crim|mixte|ass\.?\s*pl[eé]n)\.?(?:\s*\d+re?e?)?",
    re.IGNORECASE,
)

# Conseil d'État docket: "CE, n° 428318" or "CE, 21 mars 2021, n° 428318".
_FR_CONSEIL_ETAT_PATTERN = re.compile(
    r"\bCE\s*,\s*(?:(?:\d{1,2}\s+\w+\s+\d{4})\s*,\s*)?n[°º]\s*(?P<num>\d{5,7})\b",
    re.IGNORECASE,
)

# ECLI:FR: (Conseil d'État, Cour de cassation, Conseil constitutionnel, …).
_FR_ECLI_PATTERN = re.compile(
    r"\bECLI:FR:(?P<court>[A-Z]{1,6}):(?P<year>\d{4}):(?P<ordinal>[A-Za-z0-9._-]+)\b",
)

# ─── Italy ────────────────────────────────────────────────────────────────

# Codice article: "art. 2043 c.c." / "art. 575 c.p." / "art. 1321 C.C."
# Supports common codice abbreviations: c.c. (civile), c.p. (penale),
# c.p.c. (procedura civile), c.p.p. (procedura penale), c.nav. (navigazione).
# No trailing \b — `.` is non-word, so \b after it would fail when followed
# by whitespace and the regex would backtrack to drop the trailing dot.
_IT_CODICE_ARTICLE_PATTERN = re.compile(
    r"\b[Aa]rt(?:icolo|\.)?\s+\d+(?:-\w+)?(?:,?\s*comma\s+\d+)?\s+"
    r"(?P<codice>[Cc]\.?\s*[cp]\.?(?:\s*[cp]\.?)?)",
)

# Cassazione judgment: "Cass. civ. n. 1234/2020" / "Cass. pen., sez. III, n. 5678/2019".
# Matches the common "Cass. <branch> n. <ordinal>/<year>" shape.
_IT_CASS_PATTERN = re.compile(
    r"\bCass(?:azione|\.)\s*(?:civ|pen|sez\.?\s*[IVX]+|lav|trib|unite?)\.?(?:\s*,?\s*sez\.?\s*[IVX]+)?\s*,?\s*n\.?\s*(?P<num>\d{1,6})/(?P<year>\d{4})\b",
    re.IGNORECASE,
)

# Consiglio di Stato: "Cons. Stato, Sez. IV, n. 1234/2020".
_IT_CONSIGLIO_STATO_PATTERN = re.compile(
    r"\bCons(?:iglio)?\.?\s+(?:di\s+)?Stato\s*,?\s*(?:Sez\.?\s*[IVX]+)?\s*,?\s*n\.?\s*(?P<num>\d{1,6})/(?P<year>\d{4})\b",
    re.IGNORECASE,
)

# ECLI:IT: national ECLI scheme for Italian courts.
_IT_ECLI_PATTERN = re.compile(
    r"\bECLI:IT:(?P<court>[A-Z]{2,8}):(?P<year>\d{4}):(?P<ordinal>[A-Za-z0-9._-]+)\b",
)

# Article references: "Art. 8 EMRK", "Art. 261bis StGB", "Art. 1 Abs. 2 OR"
#
# The trailing token is the statute's SHORT TITLE (`BV`, `ZGB`, `StGB`), which
# is what makes the reference addressable — see `_LEGAL_ABBREVIATION_SHAPE`.
# `article` and `abbrev` are captured so `normalize_citation` can mint an
# `abbrev_art:` key without re-parsing the matched text.
_ARTICLE_PATTERN = re.compile(
    r"\bArt\.?\s+(?P<article>\d+(?:bis|ter|quater|quinquies|sexies)?)"
    r"(?:\s+(?:Abs|al|cpv)\.?\s+(?P<paragraph>\d+))?"
    r"(?:\s+(?:lit|let)\.?\s+(?P<letter>[a-z]))?"
    r"\s+(?P<abbrev>[A-ZÄÖÜ][A-Za-zÄÖÜäöü]+)\b",
)

# A statute short title carries AT LEAST TWO capitals: BV, OR, ZGB, StGB,
# SchKG, EMRK, LugÜ, MWSTG. This is a SHAPE test, not a dictionary — we never
# assert what an abbreviation means, only that it is shaped like one.
#
# Why it is needed: `_ARTICLE_PATTERN`'s trailing token is positional, so an
# article reference at the end of a clause ("... nach Art. 5 Dieses Gesetz ...")
# captures an ordinary capitalized German word. Those have exactly one capital
# and are rejected here, so they never mint a key and never become an edge.
_LEGAL_ABBREVIATION_SHAPE = re.compile(r"^(?=(?:.*[A-ZÄÖÜ]){2})[A-ZÄÖÜ][A-Za-zÄÖÜäöü]*$")


def is_legal_abbreviation(token: str) -> bool:
    """True when `token` is SHAPED like a statute short title (>= 2 capitals)."""
    return bool(_LEGAL_ABBREVIATION_SHAPE.match(token))


# Named Swiss statutes (standalone abbreviations)
_STATUTE_ABBREVIATIONS = frozenset(
    {
        "OR",
        "ZGB",
        "StGB",
        "SchKG",
        "VwVG",
        "BGG",
        "BV",
        "EMRK",
        "IPRG",
        "DSG",
        "MwStG",
        "DBG",
        "UWG",
        "KAG",
        "BankG",
        "FINMAG",
        "BEHG",
        "GwG",
        "ArG",
        "KKG",
        "PrHG",
        "URG",
        "PatG",
        "MSchG",
        "BGFA",
        "LugÜ",
        "FusG",
        "MWSTG",
    }
)


def extract_citations(text: str) -> list[Citation]:
    """Extract legal citations from text.

    Returns a deduplicated, sorted list of Citation objects.
    """
    if not text:
        return []

    citations: list[Citation] = []

    for m in _SR_PATTERN.finditer(text):
        citations.append(
            Citation(
                text=m.group(0),
                citation_type="sr",
                start=m.start(),
                end=m.end(),
                metadata={"sr_number": m.group(1)},
            )
        )

    for m in _BGE_PATTERN.finditer(text):
        citations.append(
            Citation(
                text=m.group(0),
                citation_type="bge",
                start=m.start(),
                end=m.end(),
            )
        )

    for m in _AT_BGBL_PATTERN.finditer(text):
        part = m.group("part") or m.group("part_word")
        number = m.group("number") or m.group("number_word")
        year = m.group("year") or m.group("year_word")
        metadata = {"country": "AT", "number": number, "year": year}
        if part:
            metadata["part"] = part.upper()
        citations.append(
            Citation(
                text=m.group(0),
                citation_type="at_bgbl",
                start=m.start(),
                end=m.end(),
                metadata=metadata,
            )
        )

    for m in _EU_REGULATION_PATTERN.finditer(text):
        citations.append(
            Citation(
                text=m.group(0),
                citation_type="eu_regulation",
                start=m.start(),
                end=m.end(),
            )
        )

    for m in _EU_DIRECTIVE_PATTERN.finditer(text):
        citations.append(
            Citation(
                text=m.group(0),
                citation_type="eu_directive",
                start=m.start(),
                end=m.end(),
            )
        )

    for m in _CELEX_PATTERN.finditer(text):
        citations.append(
            Citation(
                text=m.group(0),
                citation_type="eu_celex",
                start=m.start(),
                end=m.end(),
                metadata={
                    "celex": m.group(0),
                    "sector": m.group("sector"),
                    "year": m.group("year"),
                    "descriptor": m.group("descriptor"),
                    "doc_number": m.group("doc"),
                },
            )
        )

    for m in _ECLI_EU_PATTERN.finditer(text):
        court_by_code = {"C": "court-of-justice", "T": "general-court", "F": "civil-service-tribunal"}
        citations.append(
            Citation(
                text=m.group(0),
                citation_type="eu_ecli",
                start=m.start(),
                end=m.end(),
                metadata={
                    "ecli": m.group(0),
                    "court_code": m.group("court"),
                    "court": court_by_code[m.group("court")],
                    "year": m.group("year"),
                    "ordinal": m.group("ordinal"),
                },
            )
        )

    # ─── Germany ──
    for m in _DE_BVERFGE_PATTERN.finditer(text):
        citations.append(Citation(text=m.group(0), citation_type="de_bverfge", start=m.start(), end=m.end()))
    for m in _DE_BVERFG_DOCKET_PATTERN.finditer(text):
        citations.append(
            Citation(
                text=m.group(0),
                citation_type="de_bverfg_docket",
                start=m.start(),
                end=m.end(),
                metadata={
                    "senate": m.group("senate"),
                    "proceeding_type": m.group("type"),
                    "ordinal": m.group("ordinal"),
                    "year": m.group("year"),
                },
            )
        )
    for m in _DE_BGH_PATTERN.finditer(text):
        citations.append(
            Citation(
                text=m.group(0),
                citation_type="de_bgh",
                start=m.start(),
                end=m.end(),
                metadata={"reporter": m.group("reporter")},
            )
        )
    for m in _DE_ECLI_PATTERN.finditer(text):
        citations.append(
            Citation(
                text=m.group(0),
                citation_type="de_ecli",
                start=m.start(),
                end=m.end(),
                metadata={
                    "ecli": m.group(0),
                    "court": m.group("court"),
                    "year": m.group("year"),
                    "ordinal": m.group("ordinal"),
                },
            )
        )
    for m in _DE_PARAGRAPH_PATTERN.finditer(text):
        citations.append(
            Citation(
                text=m.group(0),
                citation_type="de_paragraph",
                start=m.start(),
                end=m.end(),
                metadata={"statute": m.group("statute")},
            )
        )

    # ─── France ──
    for m in _FR_CODE_ARTICLE_PATTERN.finditer(text):
        citations.append(Citation(text=m.group(0), citation_type="fr_code_article", start=m.start(), end=m.end()))
    for m in _FR_POURVOI_PATTERN.finditer(text):
        citations.append(
            Citation(
                text=m.group(0),
                citation_type="fr_pourvoi",
                start=m.start(),
                end=m.end(),
                metadata={"number": m.group("num")},
            )
        )
    for m in _FR_CASS_PATTERN.finditer(text):
        citations.append(Citation(text=m.group(0), citation_type="fr_cassation", start=m.start(), end=m.end()))
    for m in _FR_CONSEIL_ETAT_PATTERN.finditer(text):
        citations.append(
            Citation(
                text=m.group(0),
                citation_type="fr_conseil_etat",
                start=m.start(),
                end=m.end(),
                metadata={"number": m.group("num")},
            )
        )
    for m in _FR_ECLI_PATTERN.finditer(text):
        citations.append(
            Citation(
                text=m.group(0),
                citation_type="fr_ecli",
                start=m.start(),
                end=m.end(),
                metadata={
                    "ecli": m.group(0),
                    "court": m.group("court"),
                    "year": m.group("year"),
                    "ordinal": m.group("ordinal"),
                },
            )
        )

    # ─── Italy ──
    for m in _IT_CODICE_ARTICLE_PATTERN.finditer(text):
        citations.append(
            Citation(
                text=m.group(0),
                citation_type="it_codice_article",
                start=m.start(),
                end=m.end(),
                metadata={"codice": m.group("codice").strip()},
            )
        )
    for m in _IT_CASS_PATTERN.finditer(text):
        citations.append(
            Citation(
                text=m.group(0),
                citation_type="it_cassazione",
                start=m.start(),
                end=m.end(),
                metadata={"number": m.group("num"), "year": m.group("year")},
            )
        )
    for m in _IT_CONSIGLIO_STATO_PATTERN.finditer(text):
        citations.append(
            Citation(
                text=m.group(0),
                citation_type="it_consiglio_stato",
                start=m.start(),
                end=m.end(),
                metadata={"number": m.group("num"), "year": m.group("year")},
            )
        )
    for m in _IT_ECLI_PATTERN.finditer(text):
        citations.append(
            Citation(
                text=m.group(0),
                citation_type="it_ecli",
                start=m.start(),
                end=m.end(),
                metadata={
                    "ecli": m.group(0),
                    "court": m.group("court"),
                    "year": m.group("year"),
                    "ordinal": m.group("ordinal"),
                },
            )
        )

    for m in _ARTICLE_PATTERN.finditer(text):
        # PRECISION GATE. `_ARTICLE_PATTERN`'s trailing token is positional, so
        # it matches a statute's OWN article headings as readily as a citation
        # to another statute: in the real Bundesverfassung fixture, "Art. 36
        # Einschränkungen von Grundrechten" scored as a citation to a statute
        # called "Einschränkungen". 187 of the BV's 188 `article` matches were
        # its own headings, and 98.5% of all `article` matches across the
        # golden corpus were false positives.
        #
        # Those phantoms are not harmless. They inflate `citations_count`, they
        # pad the denominator of `resolution_rate` until the graph's headline
        # honesty metric measures mostly noise, and under any ranking-based
        # resolver they would have become WRONG EDGES -- which ADR-0033 treats
        # as worse than missing ones.
        #
        # So a match that does not name an abbreviation-shaped statute is not
        # recorded as a citation at all. It is not an unresolved citation; it
        # was never a citation.
        if not is_legal_abbreviation(m.group("abbrev")):
            continue
        metadata: dict[str, Any] = {
            "article": m.group("article"),
            "abbrev": m.group("abbrev"),
        }
        # Abs./lit. subdivide WITHIN an article. They are recorded so the
        # citation text stays reconstructable, but they are deliberately not
        # part of the key: the article is the addressable unit (#573).
        if m.group("paragraph"):
            metadata["paragraph"] = m.group("paragraph")
        if m.group("letter"):
            metadata["letter"] = m.group("letter")
        citations.append(
            Citation(
                text=m.group(0),
                citation_type="article",
                start=m.start(),
                end=m.end(),
                metadata=metadata,
            )
        )

    # Deduplicate by (text, citation_type)
    seen: set[tuple[str, str]] = set()
    unique: list[Citation] = []
    for c in citations:
        key = (c.text, c.citation_type)
        if key not in seen:
            seen.add(key)
            unique.append(c)

    return sorted(unique, key=lambda c: c.start)


def normalize_citation(citation: Citation) -> str | None:
    """Return a canonical lookup key for deterministic and semi-deterministic citations.

    Returns None for fuzzy citation types that need search-based resolution.
    Key format: {type}:{value} matching citation-targets index entries.
    """
    ct = citation.citation_type
    meta = citation.metadata

    # Deterministic identifiers
    if ct == "sr" and "sr_number" in meta:
        return f"sr:{meta['sr_number']}"
    if ct == "eu_celex" and "celex" in meta:
        return f"celex:{meta['celex']}"
    if ct in ("eu_ecli", "de_ecli", "fr_ecli", "it_ecli") and "ecli" in meta:
        return f"ecli:{meta['ecli']}"
    if ct == "de_bverfg_docket":
        senate = meta.get("senate", "")
        ptype = meta.get("proceeding_type", "")
        ordinal = meta.get("ordinal", "")
        year = meta.get("year", "")
        if senate and ptype and ordinal and year:
            return f"de_docket:{senate} {ptype} {ordinal}/{year}"
    if ct == "at_bgbl" and "number" in meta and "year" in meta:
        part = str(meta.get("part") or "").lower()
        suffix = f":{part}" if part else ""
        return f"at_bgbl{suffix}:{meta['number']}/{meta['year']}"

    # Semi-deterministic (text form -> deterministic key)
    if ct == "eu_regulation":
        m = re.search(r"(\d{4})/(\d{1,4})", citation.text)
        if m:
            return f"celex:3{m.group(1)}R{m.group(2).zfill(4)}"
    if ct == "eu_directive":
        m = re.search(r"(\d{4})/(\d{1,4})", citation.text)
        if m:
            return f"celex:3{m.group(1)}L{m.group(2).zfill(4)}"
    if ct == "de_paragraph" and "statute" in meta:
        return f"de_statute:{meta['statute']}"
    if ct == "fr_pourvoi" and "number" in meta:
        return f"fr_pourvoi:{meta['number']}"
    if ct == "fr_conseil_etat" and "number" in meta:
        return f"fr_ce:{meta['number']}"
    if ct == "it_cassazione" and "number" in meta and "year" in meta:
        return f"it_cass:{meta['number']}/{meta['year']}"
    if ct == "it_consiglio_stato" and "number" in meta and "year" in meta:
        return f"it_cds:{meta['number']}/{meta['year']}"
    if ct == "it_codice_article" and "codice" in meta:
        return f"it_codice:{meta['codice'].lower().replace(' ', '')}"

    # Article references ("Art. 36 BV") -- the short title plus the article
    # number IS an identifier, provided the corpus knows what the short title
    # abbreviates. That question is answered by `citation-targets`, not here:
    # this function mints the KEY, and resolution decides whether a node with
    # that key exists. Minting a key for a norm we do not hold is correct and
    # is reported as `no_target_in_corpus`, which is a coverage gap -- not a
    # guess, and not a silent miss.
    #
    # Abs./lit. are dropped: `Art. 36 Abs. 2 BV` and `Art. 36 BV` address the
    # same article-level section, which is the finest unit sectioning produces.
    if ct == "article":
        abbrev = str(meta.get("abbrev") or "")
        article = str(meta.get("article") or "")
        if article and is_legal_abbreviation(abbrev):
            return f"abbrev_art:{abbrev}/{article}"

    # Fuzzy -- needs search-based resolution
    return None
