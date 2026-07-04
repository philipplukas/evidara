# Open-law positioning

This document records **where Evidara fits in the open-source legal / open-law
ecosystem**, who the adjacent projects are, and how Evidara distinguishes and
positions itself. It is the anchor for framing decisions (README wording,
feature priorities, what we build vs. consume). It complements
[ADR-0028](adr/adr-0028-open-core-licensing.md) (licensing) — licensing says
*how* the work is open; this says *why it is distinct*.

> Snapshot date: 2026-07. The landscape moves; re-verify before quoting
> specific figures externally.

## TL;DR

- The **open Swiss/EU legal *corpus*** layer (case law + legislation as free,
  machine-readable data) is **already well-served and largely CC0**. We do not
  compete there and we do not re-scrape it.
- Evidara's distinct contribution is the **platform / governance / interop
  layer**: turning messy, multi-jurisdiction European sources into governed,
  provenance-tracked canonical truth, with a clean canonical-vs-serving split
  and contract-first IDs — then **emitting** standard formats others can consume.
- We **compose** the existing open corpora as upstream sources rather than
  duplicating them.

## The landscape

### Directly in-niche — Swiss law (the crowded part)

| Project | What it is | License |
|---|---|---|
| [OpenCaseLaw.ch](https://opencaselaw.ch/?lang=en) | ~990k Swiss decisions (fed + cantonal) since 1875 + ~21k laws, rebuilt daily, MCP + REST API, LLM-ready, no API key | Code MIT, data CC0 |
| [entscheidsuche.ch](https://github.com/entscheidsuche/entscheidsuche-mcp) | Non-profit aggregating all published Swiss court decisions (fed + 26 cantons, DE/FR/IT); upstream for much of the scene; ships an MCP server | Open |
| [Fedlex open data](https://fedlex.data.admin.ch/) | Official Swiss federal law as open data with a SPARQL endpoint (our `country-overlays/ch` / `auth_fedlex` target) | Official open data |
| [emilie](https://github.com/veronica-builds/emilie) | "Swiss sovereign legal AI"; MCP client + local models (Apertus) | Open |
| [awesome-open-legal-switzerland](https://github.com/rnckp/awesome-open-legal-switzerland) | Curated index of the Swiss open-legal scene | — |

**Implication:** an "open, LLM-ready Swiss case-law corpus + API" is already
owned by OpenCaseLaw, for free, under CC0. Evidara must *not* position there.

### Mature reference implementations — US

| Project | What it is |
|---|---|
| [CourtListener / Free Law Project](https://github.com/freelawproject/courtlistener) | Gold-standard open legal infra: 9M+ opinions (Django/Python); reusable parts: Juriscraper, RECAP, [courts-db](https://github.com/freelawproject/courts-db). Non-profit, "free access to law." |
| Caselaw Access Project (Harvard LIL) | Large US case-law dataset effort. |

### Closest in architecture + mission — Germany

| Project | What it is |
|---|---|
| [Open Legal Data / OLDP](https://github.com/openlegaldata/oldp) | Non-profit German platform: decisions + laws, Python, Elasticsearch/Haystack search, DRF REST API with generated clients, citation-network extraction. Most similar *shape* to Evidara, but single-jurisdiction and less resourced than Free Law Project. |

### The standards layer — our opportunity

| Standard | Relevance to Evidara |
|---|---|
| [Akoma Ntoso / OASIS LegalDocML](https://en.wikipedia.org/wiki/Akoma_Ntoso) + [AKN4EU](https://op.europa.eu/en/web/eu-vocabularies/akn4eu) | XML vocabulary for legal documents; the interop target we should **export**. |
| ELI (European Legislation Identifier), ECLI (case IDs) | Stable identifiers; a natural fit for our ID-as-contract discipline (ADR-0026). [Active ELI↔AKN mapping research](https://dl.acm.org/doi/fullHtml/10.1145/3614321.3614327). |
| [EUR-Lex / CELLAR](https://polzia.com/blog/eur-lex-cellar-api-developers-guide) | EU legal open data with Atom-feed change notifications; an upstream source. |

### Adjacent (not competitors)

Rules-as-code (OpenFisca, Catala), legal NLP libraries (LexNLP, Blackstone),
document assembly (Docassemble), datasets (CUAD, Pile of Law), and the index
lists — [awesome-legal-data](https://github.com/openlegaldata/awesome-legal-data),
[awesome-legaltech](https://github.com/Vaquill-AI/awesome-legaltech),
[opensource.legal](https://opensource.legal).

## What Evidara is — and is not

**Is not:** another corpus, another single-jurisdiction case-law dataset, or a
re-scrape of Fedlex / entscheidsuche.

**Is:** a **platform** — source lifecycle, approvals, runs, reference data
(`platform-control`); raw→canonical processing to Delta truth
(`document-intelligence`); serving projections + search (`legal-search`); with a
strict **canonical-truth-vs-serving-projection** split, **contract-first**
interfaces, **provenance**, **ID-as-contract** discipline (ADR-0026), and
**multi-jurisdiction** overlays (CH/AT/DE/EU/FR/IT).

## Positioning statement

> The open, contract-first **platform** for turning messy multi-jurisdiction
> European legal sources into governed, provenance-tracked canonical truth — not
> another corpus, but the pipeline and governance layer that produces and
> maintains one, and emits open standards (Akoma Ntoso / ELI / ECLI) others can
> build on.

## Differentiation

| Evidara's edge | Why it is defensible |
|---|---|
| **Multi-jurisdiction, cross-European** overlays | Every open competitor is single-country. Cross-jurisdiction structure is the hard, unsolved part. |
| **Governance & lifecycle** (approvals, runs, canonical/projection split) | Datasets lack this; it is what a publisher or firm needs to *trust* the data, and it is the commercial wedge. |
| **Interop-first**: import + **export** ELI / ECLI / Akoma Ntoso | ID-as-contract already gets us most of the way. Emitting standards makes us infrastructure others build on, not a silo. Highest-leverage move. |
| **Compose, don't re-scrape** | Consuming entscheidsuche / OpenCaseLaw / Fedlex / EUR-Lex turns potential competitors into upstreams and signals good open-law citizenship. |

## Positioning moves

- [ ] Reframe the README front door around platform / governance / multi-jurisdiction / interop — explicitly *not* "another Swiss dataset."
- [ ] Make **standards export** (Akoma Ntoso + ELI/ECLI) a headline feature of `document-intelligence` / `contracts`.
- [ ] **Consume, credit, and link** entscheidsuche / OpenCaseLaw / Fedlex / EUR-Lex as sources; record upstream terms per ADR-0028 §5.
- [ ] Reach out to those maintainers — collaboration beats competition in a small scene.
- [ ] Get listed in [awesome-legal-data](https://github.com/openlegaldata/awesome-legal-data), [awesome-open-legal-switzerland](https://github.com/rnckp/awesome-open-legal-switzerland), [awesome-legaltech](https://github.com/Vaquill-AI/awesome-legaltech), [opensource.legal](https://opensource.legal).
- [ ] Keep commercial positioning aligned with the gap: the *data* is free/commoditized; a governed, SLA-backed, multi-jurisdiction *platform* is not (see ADR-0028 dual-license).

## The one honest caveat

Because the corpus layer is already free and CC0, Evidara's differentiation
lives **entirely** in the platform / governance / interop layer. That layer must
be genuinely strong — "OpenCaseLaw with an approvals screen" would not stand
out. The multi-jurisdiction + interop story is the hard-to-copy part and is
where to double down.

## References

- [CourtListener](https://github.com/freelawproject/courtlistener) ·
  [Free Law Project tools](https://free.law/open-source-tools/)
- [Open Legal Data / OLDP](https://github.com/openlegaldata/oldp)
- [OpenCaseLaw.ch](https://opencaselaw.ch/?lang=en) ·
  [entscheidsuche-mcp](https://github.com/entscheidsuche/entscheidsuche-mcp) ·
  [Fedlex data](https://fedlex.data.admin.ch/)
- [awesome-open-legal-switzerland](https://github.com/rnckp/awesome-open-legal-switzerland) ·
  [awesome-legal-data](https://github.com/openlegaldata/awesome-legal-data)
- [Akoma Ntoso](https://en.wikipedia.org/wiki/Akoma_Ntoso) ·
  [AKN4EU](https://op.europa.eu/en/web/eu-vocabularies/akn4eu) ·
  [ELI↔AKN mapping](https://dl.acm.org/doi/fullHtml/10.1145/3614321.3614327)
- ADR-0028 — open-core licensing; ADR-0026 — ID naming policy
