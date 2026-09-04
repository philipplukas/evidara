# ADR-0054: Semantic retrieval as a measured cascade

## Status

Proposed

## Date

2026-09-04

## Context

### What retrieval does today

Evidara's search is purely lexical. `legal-search/api/src/modules/search/search-relevance.config.ts:15`
holds the whole of it — BM25 over weighted fields (`title^4`, `authority_name^3`,
`official_citation^3`, `structural_path^2`, `regeste^2`, `content`, `content_preview`,
`docket_number^2`) plus `match_phrase` boosts on five of them, against index-level BM25
defaults (`k1=1.2`, `b=0.75`).

There is no vector anywhere in the system. `documents-index.mapping.ts` — the canonical
mapping every producer derives from — defines no `knn_vector` field, nothing computes an
embedding, and no query issues a kNN clause. This is not a gap someone forgot to close; it
is the honest state of a platform that has been building acquisition, not ranking.

### Why lexical alone cannot answer the question the platform exists to answer

ADR-0033's acceptance test is the dog question: a lawyer asks something like *"darf ich
meinen Hund im Restaurant mitnehmen"* and expects the ZH Hundegesetz.

BM25 fails this shape by construction. The query's content words — *Restaurant*,
*mitnehmen* — largely do not occur in the statute, which legislates in terms of
*Mitführen* and *öffentlich zugängliche Räume*. Lexical retrieval requires the asker to
already know the legislature's vocabulary, which is precisely the knowledge a lay or
cross-jurisdictional question lacks. The field weights above cannot fix this: weighting a
term higher does not help when the term is absent.

So semantic retrieval is not a nice-to-have layered on a working product. It is on the
critical path of this project's own stated acceptance criterion.

### The constraint that outranks all of it

The live index holds **6 documents** (`documents-000001`, measured 2026-09-04).

No retrieval quality claim is measurable at that size. Any NDCG, recall or win-rate
computed over six documents is noise, and a semantic pipeline tuned against it would be
tuned against nothing. This ADR therefore decides a *design and a build order*, and
explicitly refuses to decide model choices that can only be settled by measurement.

That ordering is the same one ADR-0033 §4 imposes when it says not to build the MCP server
first: the dependency graph, not the appeal of the component.

### What the research says, as of 2026-09

Three shifts matter for the design, and two legal-domain findings matter more.

**Representation is a cascade, not a choice.** Learned sparse (SPLADE and its 2026
descendants — expanded-vocabulary variants, SAE-derived concept spaces) produces sparse
vectors that run on an inverted index and stay inspectable. Late interaction (ColBERT)
keeps a vector per token; SPLATE makes it affordable by mapping ColBERTv2's frozen
embeddings into a sparse space, reaching PLAID ColBERTv2 quality by reranking ~50
candidates in under 10ms. Dense bi-encoders remain the cheap first stage. The engineering
question is the cascade, not the retriever.

**Chunking is a representation decision, not preprocessing.** *Late chunking* embeds a
whole document through a long-context model and chunks the token embeddings before
pooling, so each chunk's vector carries whole-document context, with no retraining.
*Contextual Retrieval* solves the same problem in text space by prepending generated
context to each chunk. 2026 adds adaptive chunking — selecting the method per document.

For statutes this is decisive rather than incremental. An article embedded alone is often
meaningless: `Art. 7` of an ordinance may be a bare sentence whose subject lives in the
scope article. Embedded with the rest of the law in attention, it is a usable
representation of a rule.

**Rerankers acquired reasoning, and a strong counterargument.** Rank1 was the first
reasoning reranker trained on distilled reasoning traces, and generalises multilingually
despite English-only training data; *Rerank Before You Reason* finds reranking lowers
end-to-end token cost in agentic search. Against that, published results show a
well-trained bi-encoder beating expensive LLM rerankers at **over 200× less test-time
compute**. "Add an LLM reranker" is a cost curve to measure, not a conclusion.

**Legal finding 1 — retrieval sets the ceiling.** The Legal RAG Bench work concludes that
retrieval quality, not reasoning ability, is the primary driver of legal RAG performance.
This is direct external support for ADR-0033's bet that a thorough data platform is what
makes the AI use cases easy.

**Legal finding 2 — legal retrieval benchmarks are contaminated.** MLEB (the Massive Legal
Embedding Benchmark, 10 datasets across jurisdictions and task types) found that scores on
prior legal benchmarks *did not correlate* with MLEB scores, with leakage of evaluation
data into commercial embedding models' training sets a suspected cause, alongside
straightforwardly mislabeled query–passage pairs in public sets.

The practical corollary is visible in the market: two vendors each currently claim the
best legal embedding model — ZeroEntropy's zembed-1 (0.6723 NDCG@10, "+31.8% over all
competitors") and Isaacus's Kanon 2 Embedder ("+17 points" over frontier general models).
Both figures are published by the vendor of the model they rank first, and one of those
same posts is where the leakage finding comes from. Neither is evidence about Swiss
statutes in German.

**The most actionable paper for this repo is CRAwLeR** (Cross-Reference Aware Legal
Retrieval, Danish statutory law). It treats statute law as an interconnected graph and
uses the cross-reference network between norms as part of retrieval, on the observation
that understanding one provision usually requires the provisions it cites.

Evidara already holds that graph. The mapping defines `subordinate_to` and `delegates_to`;
the cluster runs a `citations` index (504 documents) and `citation-targets`;
`resolveCitationTargets()` in the projections adapter resolves normalised references; and
there is a whole `norm-hierarchy` module with `structural_path` already carrying weight in
the lexical ranking. Cross-reference-aware retrieval is a scoring change over data
acquisition is already extracting — not a new subsystem.

### The failure mode semantic search introduces

This is the part that must not be discovered in production.

BM25 abstains for free. A query with no lexical overlap returns nothing, and "no results"
is a true statement about the corpus. A kNN retriever **never abstains**: it returns its
`k` nearest neighbours whatever the query, so a corpus that does not contain the Zürich
dog ordinance will happily return the *Berne* one, or a tangentially related federal
animal-welfare provision, ranked first and worded plausibly.

ADR-0033 states the acceptance test in two halves — the dog question answered over a
corpus assembled through the platform, **or refused correctly because the ordinance is not
in it**. Semantic retrieval makes the second half strictly harder, and it is the half that
protects a lawyer from a confident wrong answer. ADR-0039 makes the same point about the
marketing page: a visitor who gets wrong answers presented as right ones is the failure
mode worse than having no product.

The codebase already distinguishes these epistemics in one place —
`legal-search/api/src/modules/search/opensearch.adapter.ts:231`: *"A query that could not
be executed is NOT an empty result set (#551)."* Semantic retrieval adds a third state to
that same axis: **a result set that exists but means nothing**. There is no `min_score` and
no abstention anywhere in the search path today.

### The measurement gap

`eval/` exists and is real: `queries.csv` carries 29+ German-language legal queries tagged
by task type (`section_extraction`, `holding_extraction`, `temporal_version`,
`source_classification`, `citation_chain`, `cross_reference`), with `as_of_date`,
difficulty and pinpoint flags; `score_eval.py` scores correctness, citation
precision/recall and temporal accuracy into a weighted composite.

But it scores **answers, not retrieval**. There is no NDCG@k, no recall@k, no measurement
of the candidate set a ranker produced. Against the finding that retrieval sets the
ceiling, that means a failure today cannot be attributed: an answer scored wrong might be
a retrieval miss or a generation error, and nothing separates them. The corpus is also
Austrian (RIS), which is the right shape and the wrong jurisdiction for the dog question.

## Decision

Build semantic retrieval as a **measured cascade**: a staged pipeline in which every stage
has an explicit contract, every stage is separately observable, every knob is versioned in
one place, and no stage may be enabled without evidence from a retrieval-level harness.

The three properties are structural, not aspirational — each is a named mechanism below.

### D1 — The cascade, and its stage contracts

Four stages, each with a declared input, output and failure mode:

| Stage | Input | Output | Abstains by |
|---|---|---|---|
| 1. Candidate generation | query + filters | ≤200 candidates | returning fewer, never padding |
| 2. Fusion | ranked lists per retriever | one ranked list | — |
| 3. Reranking | top-N candidates | reordered top-K | — |
| 4. Gating | scored top-K | results **or** an explicit refusal | score floor + margin |

Stage 1 runs the retrievers in parallel: today's BM25, plus dense kNN, plus (later) the
cross-reference expansion of D5. Stage 2 fuses with rank-based fusion rather than raw score
mixing, because BM25 scores and cosine similarities are not commensurable and normalising
them invents a comparison the numbers do not support.

**Lexical retrieval is never removed from the cascade.** `Art. 261bis StGB` and
`BGE 145 IV 137` must resolve exactly, and citations are what dense retrieval is worst at.
The existing `official_citation^3` and `docket_number^2` weights stay load-bearing.

### D2 — Optimizable: one config object, versioned, and an offline replay path

Every tunable lives in one module beside the existing weights —
`search-relevance.config.ts` already establishes this pattern and its own docstring says
the parameters are centralised "so they can be adjusted in one place once the corpus is
large enough for meaningful evaluation". That moment is what this ADR is preparing for.

The extended config carries a **`retrieval_config_version`** string. That version is:

- stamped into every search response (internal field, not user-facing),
- recorded on every eval run,
- and required to change whenever any knob changes.

Without it, a relevance number cannot be attributed to a configuration, and A/B results
become folklore. With it, "which config produced this ranking" is answerable from a log
line.

Tuning happens **offline against captured candidate sets**, not against the live cluster:
stage 1 output is replayable, so fusion weights, rerank depth and the D4 thresholds can be
swept without re-running retrieval or paying for reranking on every trial.

### D3 — Observable: per-stage telemetry, and the query itself as data

Each stage emits, per query: elapsed ms, candidates in, candidates out, and the score
distribution (min / median / max) it produced. Two things fall out that are currently
invisible:

- **Where latency goes.** A cascade with a reranker has a cost profile; one number for
  "search took 400ms" cannot say whether to cut rerank depth or fix an ANN parameter.
- **Whether a stage is doing anything.** A fusion stage whose dense list never contributes
  a top-10 result is a stage that can be deleted. Only per-stage counts reveal that, and
  ADR-0052's rule applies directly — a declared component with no observable effect reads
  as working and is not.

The cluster already runs OpenSearch **Query Insights** (`top_queries-*` indices, ~2,900
records/day), so top-query capture exists and is unused by the application. Real queries
are the only source of the evaluation set that matters; D6 says what may be done with
them.

### D4 — Testable, part one: the abstention gate is a first-class, tested behaviour

The gating stage refuses on two conditions, both configurable in D2's object:

1. **Absolute floor** — the top fused score is below a threshold.
2. **Margin collapse** — the top-K scores are indistinguishable from each other, which is
   what "nearest neighbours of an unrelated query" looks like.

A refusal is a distinct response state, not an empty list — the axis
`opensearch.adapter.ts:231` already established for #551.

Per AGENTS.md, this guard ships with a test that fails when the guard is removed: the
suite contains a query whose subject is **provably absent** from the fixture corpus, and it
asserts a refusal. Delete the gate and that test must go red. The same file's warning about
fixture calibration applies with force here — a floor tuned to one sample will withhold
real answers on the next corpus, so the threshold is a versioned knob (D2) with its own
regression case, not a constant someone picked.

### D5 — Cross-reference expansion, because the graph already exists

Implement CRAwLeR's insight over Evidara's own citation graph: after stage 1, expand the
candidate set along `subordinate_to`, `delegates_to` and the `citations` /
`citation-targets` indices, with expanded candidates carrying a distinguishable provenance
so stage 3 can weight them differently and stage 4 can report them as derived.

This is deliberately sequenced **before** any model-selection work. It requires no
embedding, no GPU and no vendor: it is a scoring change over data the acquisition platform
already produces, and it is the one place where the newest research direction is *cheaper*
for this repo than the conventional one.

### D6 — Testable, part two: retrieval metrics, on our own held-out data

`eval/` gains a retrieval layer beside its answer layer: recall@k and NDCG@k over a
labelled candidate set, reported per `task_type` so a `citation_chain` regression cannot
hide behind a `section_classification` improvement.

Given MLEB's leakage finding, **published leaderboard scores are treated as marketing, not
evidence.** The only number that governs a decision here is one measured on Evidara's own
held-out Swiss queries. Two rules follow:

- The Swiss golden set is built from real queries (D3's Query Insights capture) and from
  the ADR-0033 dog question family, labelled by a human, and **never** sent to a model
  vendor for training or fine-tuning.
- A held-out slice is never used for tuning, only for the final read.

### D7 — Chunking: late chunking, decided now because it is expensive later

Embeddings are produced in `document-intelligence` as a pipeline stage, using **late
chunking**: the document goes through a long-context model once and section-level vectors
are pooled from its token embeddings, rather than each section being embedded standalone.

This is decided before implementation because it is a data-shape commitment. Re-embedding
a large corpus to change chunking strategy is exactly the cost the platform exists to
avoid paying twice, and the `sections` index shows section-level granularity is already
the intended unit.

ADR-0005 makes this materially cheaper than it sounds elsewhere: search is a *serving
layer only*, rebuilt from canonical Delta truth, so vectors are derived data and
re-embedding is a reindex rather than a migration. The commitment being made here is to
the *pipeline stage*, not to an irreversible corpus state — which is why the model choice
can safely stay undecided while the chunking strategy cannot.

### D8 — The vector field is added *with* its producer, never before

Per ADR-0052 and the AGENTS.md review rule, a `knn_vector` field in
`documents-index.mapping.ts` with nothing writing it is worse than no field: an empty
vector field reads as *"this corpus has no semantic index"* to every consumer, which is
indistinguishable from *"semantic search found nothing"*.

The mapping change, the `document-intelligence` producer, and the `PRODUCERS` registry
entry in `mapping-drift.integration.spec.ts` land in the same change. The mapping's single
source of truth is not weakened for this: index creation is first-writer-wins, so a second
creation path does not merely disagree — it silently wins.

### D9 — The build order, gated on corpus size

Semantic retrieval is not enabled by a date. Each step's exit condition is the evidence
that makes the next one measurable:

| Step | Gate to start |
|---|---|
| 1. Retrieval metrics in `eval/` (D6) | none — do this now, it measures the *current* BM25 baseline |
| 2. Cross-reference expansion (D5) | step 1 green, so the change can be shown to help |
| 3. Swiss golden set from real queries (D6) | a corpus with enough documents for a query to have a wrong answer available |
| 4. Late-chunked embeddings + mapping (D7, D8) | step 3 exists, so model choice is decidable |
| 5. Fusion + gating (D1, D4) | step 4 |
| 6. Reranking (stage 3) | steps 1–5, and a measured cost curve — the 200× finding says this may not pay |

Step 1 is available immediately and is worth doing on its own terms: it gives the lexical
baseline a number, and without a baseline no later improvement can be claimed.

## Consequences

### What gets better

- The dog question becomes answerable in the way ADR-0033 phrases it, rather than only for
  a user who already knows the statutory vocabulary.
- A wrong answer becomes attributable. Retrieval metrics separate "the ranker never
  surfaced it" from "the answer stage mishandled it", which today are one indistinguishable
  failure.
- The citation graph starts paying for itself in ranking, not only in the document-detail
  UI.
- Today's BM25 gets a baseline number for the first time.

### What gets harder

- **Abstention becomes a design problem instead of a free property.** This is the real
  cost of this ADR, and D4 is the whole of the mitigation.
- Each stage is a place to be wrong, and a cascade can be slower and worse than BM25 if
  fusion is mis-weighted. D3's per-stage telemetry exists so that is visible rather than
  inferred.
- Embeddings add a pipeline stage with real compute cost and a re-embedding liability on
  every model change.
- The `documents` mapping gains a field whose absence in older indices must be handled —
  reindex/cutover per the AGENTS.md rule, never a weakened query that tolerates the drift.

### Not covered

- **Model selection.** Deliberately undecided; D6 says what evidence would decide it, and
  the corpus does not yet support producing that evidence.
- **Whether reranking pays at all.** Step 6 is gated on a cost curve, not assumed.
- **Generative answering.** This ADR ends at a ranked, gated result set. What consumes it
  is ADR-0033's business.
- **Multilingual parity.** Swiss federal law is the same norm in German, French and
  Italian, and no benchmark surveyed evaluates that. It is a known unmeasured risk, named
  here rather than assumed away.
- **The MCP server.** Still not first (ADR-0033 §4).

## References

- ADR-0005 — OpenSearch as a serving layer only; why vectors are rebuildable derived data
- ADR-0033 — agentic legal reasoning; the dog question and the build order
- ADR-0039 — wrong answers presented as right ones as the failure mode worse than none
- ADR-0052 — declared means produced (D8's rule)
- #551 — a query that could not be executed is not an empty result set
- #675, #713 — why the mapping has exactly one source of truth
- `legal-search/api/src/modules/search/search-relevance.config.ts` — today's ranking, in full
- `eval/queries.csv`, `eval/score_eval.py` — the answer-quality harness this extends
- SPLATE (SIGIR) — sparse late interaction; ColBERTv2 quality at ~10ms rerank
- Late Chunking (arXiv:2409.04701) — D7
- Rank1 (arXiv:2502.18418), *Rerank Before You Reason* (arXiv:2601.14224) — reasoning rerankers
- CRAwLeR (arXiv:2606.21676) — cross-reference aware legal retrieval; D5
- MLEB / Legal RAG Bench — benchmark contamination; retrieval sets the ceiling
