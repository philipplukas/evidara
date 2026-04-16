"""Legal citation extraction for Swiss and EU legal documents.

Extracts references to:
- Swiss federal law (SR numbers): e.g., "SR 210", "SR 311.0"
- Swiss BGE decisions: e.g., "BGE 147 III 49", "BGE 148 IV 234"
- EU regulations/directives: e.g., "Regulation (EU) 2016/679", "Directive 2013/36/EU"
- EU CELEX IDs: e.g., "32016R0679" (GDPR), "32019L0790" (Copyright Directive)
- EU ECLI identifiers: e.g., "ECLI:EU:C:2019:218", "ECLI:EU:T:2020:338"
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

# Article references: "Art. 8 EMRK", "Art. 261bis StGB", "Art. 1 Abs. 2 OR"
_ARTICLE_PATTERN = re.compile(
    r"\bArt\.?\s+\d+(?:bis|ter|quater|quinquies|sexies)?(?:\s+(?:Abs|al|cpv)\.?\s+\d+)?(?:\s+(?:lit|let)\.?\s+[a-z])?\s+[A-ZÄÖÜ][A-Za-zÄÖÜäöü]+\b",
)

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

    for m in _ARTICLE_PATTERN.finditer(text):
        citations.append(
            Citation(
                text=m.group(0),
                citation_type="article",
                start=m.start(),
                end=m.end(),
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
