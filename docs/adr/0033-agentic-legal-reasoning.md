# ADR-0033: Agentic Legal Reasoning — RAG to Enter, Graph to Reason

## Status

Accepted

## Date

2026-07-14

## Context

### The WHY this ADR exists to serve

The bet behind Evidara is that **a thorough data platform for law makes AI use cases
easy** — that once the corpus is structured, connected, and trustworthy, the agentic
layer on top is thin. This ADR makes that bet concrete, and falsifiable, by fixing the
question the platform must be able to answer:

> **Can the city ban a certain thing for dogs, year-round?**

It is a good acceptance test precisely because it is *not a retrieval question*. It is a
reasoning-over-hierarchy question, and answering it correctly requires five layers of
Swiss law and the relationships between them:

| Layer | What decides the question | Status today |
|---|---|---|
| **Municipal** — the city's Hundereglement (the act being challenged) | the ordinance itself | **no acquisition path exists at all** |
| **Cantonal** — the Hundegesetz: does it *delegate* this competence to communes? | cantonal statute | all cantonal templates `enabled: false` |
| **Federal** — Tierschutzgesetz / Tierschutzverordnung: is the field preempted? | TSchG / TSchV | provider works; never run |
| **Constitutional** — BV Art. 5 (Legalitätsprinzip), Art. 36 (Verhältnismässigkeit) | BV Art. 36 as a *citable unit* | BV is indexed as **2 sections**, language `it` |
| **Case law** — has the BGer ruled on year-round bans / communal competence? | BGer decisions | all `ch_court_decisions` templates `enabled: false` |

**One of five layers, and it is broken.** That is the honest baseline.

### Why a general LLM cannot answer this — and cannot know that it can't

A general model will produce a fluent answer citing a plausible-sounding cantonal
provision that does not exist. It has no notion of which norm outranks which, which
version was in force, or whether the commune held delegated competence at all. The
failure is not that it is unsure; the failure is that it is **confidently wrong**, which
in a legal-research product is worse than silence.

### Why generic RAG does not fix it

Vector search over the corpus fails here for a structural reason, not a tuning reason.
The phrase *"can the city ban X for dogs all year"* has near-zero lexical **or semantic**
overlap with the text that actually decides it — a delegation clause in a cantonal
statute, and a proportionality test in BV Art. 36. No embedding walks that path, because
the path is not a similarity relation. It is a **legal-hierarchy relation**.

### What we actually have (verified against the running cluster, 2026-07-14)

- `documents-000001`: 6 docs. `sections`: **4**. `citations`: **504**.
  **`citation-targets`: does not exist.** Citations are extracted as *strings*, never
  resolved into *edges*. The graph does not exist.
- `normalize_citation` (`document-intelligence/.../nlp/citation_extractor.py`) already
  emits canonical keys — `sr:210`, `celex:...` — keyed to the *Systematische
  Rechtssammlung* number, which is the authoritative identifier for Swiss federal law.
  **The edge format is designed. It was simply never built.**
- Search is `multi_match` — **BM25 keyword only, no embeddings**. But OpenSearch already
  has `opensearch-knn`, `opensearch-ml` and `opensearch-neural-search` installed, so
  hybrid retrieval is a pipeline-and-model job, not new infrastructure.
- Documents carry `effective_date` but **no repeal/until date** — "in force on
  2019-06-01" is not answerable.
- Documents carry `jurisdiction_ids` / `authority_ids` but **no `level`, and no
  subordination relation**. Nothing encodes that cantonal law sits beneath federal.
- **2,110 Swiss municipalities are seeded as jurisdictions** (`jur_ch_gemeinde_*`,
  BFS-keyed) with **zero** authorities, templates or providers. The municipal layer is
  modelled and unreachable — and the demo question lives exactly there.
- There is **no MCP server**.

(ADR-0022's "agentic CLI control surface" is a different surface: it bounds *operator*
actions against platform-control. It is not the legal-research reasoning layer and should
not be conflated with it.)

## Decision

### 1. The architecture: RAG to enter, graph to reason

Legal reasoning has a **known shape**. The agent does not need to guess the path, because
the path is structural. Retrieval is the entry point; traversal is the reasoning.

```
1. CLASSIFY   place (city) · domain (dog / police law) · question type
                (competence + proportionality)
2. ANCHOR     hybrid search → the municipal ordinance        ← RAG belongs HERE, and only here
3. WALK UP    ordinance → which cantonal law delegates this?  ← deterministic traversal
              → which federal law constrains it? → BV Art. 36
4. WALK OUT   citation graph → BGer decisions citing those    ← deterministic traversal
5. REASON     competence test, then the Art. 36 proportionality test
6. ANSWER     every claim anchored to a section id the user can open
```

Steps 3 and 4 are **graph traversal, not embedding similarity.** This is the whole
differentiator: it is what a general model and a generic web-RAG structurally cannot do,
and it is only possible because the platform holds the hierarchy and the citation edges.

Vector search is a *lookup*, not a reasoner. We use it once, to find the anchor.

### 2. The agent must be able to refuse

Because coverage is explicit, the agent can check whether the governing ordinance is
actually in the corpus. If it is not, it **says so and stops**, rather than reaching for
the nearest plausible text. Structured coverage is the only real cure for confident
fabrication, and it is a capability a general model cannot have.

"I do not have the Hundereglement for this commune" is a *correct* answer. A fluent
citation of a provision that does not exist is not.

### 3. MCP is the tool surface

Build the tool layer **once**, as an MCP server over the existing legal-search API, so it
serves Claude Desktop (demos), the product frontend, eval harnesses, and third parties
without reimplementing retrieval each time. That is the "AI use cases become easy" thesis
made concrete and testable.

The tool set falls straight out of the workflow above:

| Tool | Purpose | Depends on |
|---|---|---|
| `search_law(query, jurisdiction?, level?, in_force_at?, lang?)` | the anchor step; hybrid BM25 + kNN | hybrid retrieval; correct `language` (#572) |
| `get_provision("Art. 36 Abs. 2 BV")` | verbatim text of one article | **article-level sections (#573)** |
| `resolve_citation(text)` | citation string → norm id | **`citation-targets` index** |
| `find_citing(id, kind=case\|law)` | the case law interpreting a provision | citation graph |
| `norm_hierarchy(jurisdiction_id)` | what governs this city, at each level | **norm-hierarchy model** |
| `check_in_force(id, date)` | the 2019 ban is judged against 2019 law | **repeal/until dates** |

Every one of those dependencies is currently missing or broken. That is the point of
writing them down.

### 4. Build order — and what NOT to build first

**Do not build the MCP server first.** It is the fun part, it demos, and over a corpus of
one mislabelled two-section document it would produce a demo that *lies convincingly* —
which is worse than one that fails. The tool layer is thin. The platform underneath is the
work.

The order is forced by the dependency column above:

1. **Article-level sectioning (#573).** Existential, not a quality nit. `get_provision`
   is impossible while the BV is 2 sections; an LLM handed a 525KB blob truncates or
   fabricates. Nothing else on this list works without it.
2. **Build the citation graph.** 504 citations extracted, zero resolved. Populate
   `citation-targets` from the keys `normalize_citation` already produces.
3. **Model the norm hierarchy** — `level` on documents, plus *subordinate-to* and
   *delegates-to* relations. The least glamorous item here and the most differentiating.
4. **Correct metadata (#572).** An agent filtering to *"Zürich cantonal law, German, in
   force"* gets nothing today, because `language` is wrong. Bad metadata does not degrade
   an AI use case gracefully — it silently returns the wrong law.
5. **Hybrid retrieval.** The plugins are installed; this is an ingest pipeline plus a
   model. Needed only for the anchor step.
6. **Then MCP.**

> Execution anchor: the endpoint-surfacing breakdown of this build order — sequenced,
> acceptance-gated, file-grounded work items (M13/M14) — lives in
> [`docs/product/reasoning-surface-work-items.md`](../product/reasoning-surface-work-items.md).

### 5. The corpus is scoped by the demo, not by ambition

M13 is rescoped from *horizontal coverage* to a **vertical slice**: the smallest corpus
that answers the dog question end to end.

- Federal: TSchG, TSchV, BV
- Cantonal: **one** canton (Zürich) — Hundegesetz + Hundeverordnung
- Municipal: **one** city (Zürich) — Hundereglement / Polizeiverordnung *(needs a new
  acquisition path — this is the hard, novel work)*
- Case law: BGer decisions on communal competence and Art. 36 proportionality

Perhaps 20–50 documents. **All of Fedlex is 10,000 documents that demo nothing.** A
vertical slice that answers one real question end to end is worth more than a horizontal
corpus that answers none — and it is the only way to discover which of the five layers is
actually hard before paying for all of them.

## Consequences

- The dog question becomes the **acceptance test** for M13 and M14. "Done" means an agent
  answers it correctly, with every claim anchored to an openable citation — or refuses,
  correctly, because the ordinance is not in the corpus.
- Municipal acquisition becomes a first-class, named gap rather than an unnoticed hole
  behind 2,110 seeded-but-unreachable jurisdictions. It is likely the hardest scraping
  problem in the project (~2,000 municipal sites, mostly PDFs, no API), and the demo
  cannot be faked without it.
- `citation-targets` and the norm hierarchy move from "someday" to blocking.
- We accept that the corpus stays small for longer, in exchange for it being *answerable*.

## Alternatives considered

**Ship an MCP server over the current corpus now.** Rejected. It is the fastest path to a
demo and the fastest path to a demo that lies. The tool layer cannot add structure the
data does not have.

**Pure vector RAG over the full corpus.** Rejected. The decisive text shares neither
lexical nor semantic surface with the question. This is a structural limitation, not a
tuning problem, and no amount of chunking or reranking fixes a missing hierarchy.

**Horizontal coverage first (all of Fedlex), reason later.** Rejected. Scaling a broken
extractor produces 10,000 documents with `sections_count: 2` and no way to tell when it
started going wrong — the exact failure mode this codebase has repeatedly shipped.
