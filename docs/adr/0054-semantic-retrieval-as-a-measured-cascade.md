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

### Evidence from Swiss legal text, not from an English benchmark

Everything above is general IR, and the section on contaminated benchmarks is a warning
against importing its numbers. One study is not general: ZHAW published (2026-06) an
evaluation built from **165,556 Swiss Federal Supreme Court decisions** (2000–2025), split
into roughly 2.4 million passages, with 26 legal questions each translated into German,
French, Italian and English — 104 query instances against ground-truth considerations.
Twelve multilingual embedding models were tested, alongside reranking, hybrid search,
language deconfounding and LLM query paraphrasing.

The headline is the reason this ADR exists:

> **73%** of queries found the correct passage in the top ten, against **19%** for keyword
> search.

That is close to a fourfold gap, measured on Swiss legal text in the languages this
platform serves, rather than on English common-law data. It is the strongest available
evidence that the lexical ceiling described above is real and not a modelling artefact.

The same study supplies the caveat, and it lands on this ADR's own stated risk: German and
English queries outperformed French and Italian, with data skew toward German
acknowledged, and the authors conclude that *"multilingual does not yet mean equally good
in every language."* Multilingual parity is therefore no longer an unmeasured risk in this
document — it is a **measured and confirmed** one, which is why D6 requires per-language
reporting rather than an average.

The study does not appear to release its dataset or code, so it justifies the direction
without supplying a harness. D6 still has to be built.

### What is already installed, and switched off

The decisive fact for the build order is not in the literature. It is in the cluster.

OpenSearch 3.7.0 is running with, among others: `opensearch-neural-search`,
`opensearch-knn`, `opensearch-ml`, `opensearch-ltr`, `opensearch-search-relevance`,
`opensearch-ubi` and `query-insights`. The hybrid query executor thread pool is live
(`_plugin_neural_search_hybrid_query_executor`, size 16), and the cluster settings read:

```
plugins.search_relevance.workbench_enabled          = true
plugins.search_relevance.scheduled_experiments_enabled = true
```

**Search Relevance Workbench is enabled on the running cluster and nothing uses it.** It
provides query sets, judgment lists, search-quality evaluation experiments, and a hybrid
search optimization experiment that sweeps 82 variants per query — `l2`, `min_max` and
`z_score` normalisation, arithmetic/harmonic/geometric combination, lexical-vs-neural
weights in 0.1 increments, and RRF across `rank_constant` values. UBI supplies the schema
from which SRW can derive *implicit* judgments out of real interaction data.

This changes what D2 and D6 are. They were specified as things to build; most of both is a
thing to **enable and configure**. An earlier draft of this ADR proposed constructing a
config-sweep harness next to a cluster that already had one, idle — which is the same
defect ADR-0052 names, seen from the other side: a capability that exists, is declared in
the plugin list, and is treated by everyone as absent.

#### And a hardware constraint that decides where embedding runs

```
name                        node.role  heap.max  ram.max
opensearch-cluster-master-0 dimr       512mb     2gb
```

One node, roles data/ingest/cluster-manager/remote-client — **no `ml` role** — while
`plugins.ml_commons.only_run_on_ml_node = true`. In-cluster model hosting will refuse to
allocate, and a 512MB heap on a 2GB node could not host a modern encoder in any case.

This is not an obstacle to route around; it settles a design question. Embedding belongs in
`document-intelligence` (D7), and the query path must stay cheap — which is exactly the
shape neural sparse **doc-only** mode has, where the model runs at ingest and query time
needs only a tokenizer and a weight lookup table.

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

### D2 — Optimizable: the cluster's own optimizer, plus one versioned config

Parameter search is **not hand-rolled**. Search Relevance Workbench is enabled on the
cluster today, and its hybrid search optimization experiment sweeps a space — 82 variants
per query across three normalisation techniques, three combination techniques, the
lexical/neural weight, and RRF `rank_constant` — that nobody would sweep by hand and
nobody should reimplement. Fusion weights are *found*, against a judgment list, not chosen.

What remains ours is attribution. Every tunable lives in one module beside the existing
weights —
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

The knobs SRW does not own — D4's abstention floor and margin, rerank depth, the D5
expansion budget — are tuned **offline against captured candidate sets** rather than
against the live cluster: stage 1 output is replayable, so a sweep costs no retrieval and
no reranking.

The division is deliberate: SRW optimises what it has a judgment list for, and anything it
cannot score stays in the versioned config with its own regression case.

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

Retrieval quality is measured with **Search Relevance Workbench**, using its query sets,
judgment lists and search-quality evaluation experiments, rather than with a parallel
harness built beside it. `eval/` keeps its answer-quality role; SRW owns recall@k and
NDCG@k over the candidate set. Judgments come from three sources SRW already supports:
human labels, imported lists, and implicit judgments derived from UBI interaction data.

Three rules constrain it, and none of them is optional:

- **Reported per language.** German, French and Italian are scored and read separately,
  never as one average. The ZHAW result is that the gap between them is real; an average
  is precisely the statistic that would hide it.
- **Reported per `task_type`**, so a `citation_chain` regression cannot hide behind a
  `section_extraction` improvement — the same axis `eval/queries.csv` already carries.
- **Our own data decides.** Given MLEB's leakage finding, published leaderboard scores are
  treated as marketing, not evidence. The Swiss golden set is built from real captured
  queries and the ADR-0033 dog-question family, labelled by a human, and **never** sent to
  a model vendor for training or fine-tuning. A held-out slice is never used for tuning,
  only for the final read.

The one thing SRW does not do is measure the D4 refusal, because a judgment list scores
rankings and a refusal is the absence of one. That case stays in `eval/` as the named test
D4 requires.

### D7 — Chunking: late chunking, decided now because it is expensive later

Embeddings are produced in `document-intelligence` as a pipeline stage, using **late
chunking**: the document goes through a long-context model once and section-level vectors
are pooled from its token embeddings, rather than each section being embedded standalone.

That `document-intelligence` is the host is now forced rather than preferred. The
OpenSearch node has no `ml` role, `plugins.ml_commons.only_run_on_ml_node` is `true`, and
its heap is 512MB on a 2GB node — in-cluster model hosting cannot allocate and should not
be made to. Embedding is ingest-time work in a Python pipeline that already exists.

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

### D10 — What may be a candidate representation, and what may not

The model is still not chosen — D6 says what evidence would choose it. But the field of
candidates is narrowed now, on two criteria that no amount of measurement will change.

**Licence first.** `jina-embeddings-v3` is strong, supports late chunking natively, and is
released **CC-BY-NC**: non-commercial. It is out, and it is named here so nobody
rediscovers it, benchmarks it, and then finds out. Commercially usable candidates:
**BGE-M3** (MIT), `multilingual-e5-large` (MIT), GTE-multilingual, and the OpenSearch
neural sparse models.

**Then coverage of the languages Swiss law is actually in.** OpenSearch's own
`multilingual-v1` neural sparse model is benchmarked on 16 languages including French —
and **not German, and not Italian**. That is not disqualifying, but it means the model
OpenSearch ships for this purpose is untested on the majority language of this corpus, and
D6's per-language reporting is how that gets settled rather than assumed.

Two candidates get named because they are structurally interesting, not because they win:

- **BGE-M3** produces dense, learned-sparse and ColBERT-style multi-vector representations
  from a single model, over 100 languages at 8192 tokens. For the D1 cascade that means
  *one* ingest pass in `document-intelligence` feeds all three retrieval arms, instead of
  three pipelines to keep consistent. If it measures acceptably on German, it is the
  cheapest possible shape for this design.
- **Neural sparse in doc-only mode** is the option that fits the hardware. It searches on
  Lucene's inverted index rather than a vector store, its `(token, weight)` output is
  inspectable in a way a dense vector is not — which matters for a legal product that must
  explain itself — and the query path needs no model.

**SwissBERT / SentenceSwissBERT** (ZurichNLP) has language adapters for German, French,
Italian and Romansh and is the only model built for Switzerland's actual language
situation. It is trained on news rather than law and is small, so it is a candidate to
measure, never a default.

Nothing here is a decision to adopt. It is a decision about what enters the comparison,
and it exists so that the comparison in D6 is short enough to actually run.

### D9 — The build order, gated on corpus size

Semantic retrieval is not enabled by a date. Each step's exit condition is the evidence
that makes the next one measurable:

| Step | Gate to start |
|---|---|
| 1. Turn on UBI + Query Insights capture, build the first query set (D3, D6) | none — configuration on a cluster that already runs both |
| 2. SRW search-quality experiment against today's BM25 (D6) | step 1 — this is the baseline, and it is *configuration*, not construction |
| 3. Cross-reference expansion (D5) | step 2 green, so the change can be shown to help |
| 4. Swiss golden set from real queries, per language (D6) | a corpus large enough for a query to have a wrong answer available |
| 5. Late-chunked embeddings + mapping (D7, D8, D10) | step 4 exists, so model choice is decidable |
| 6. SRW hybrid optimizer over fusion; then gating (D1, D2, D4) | step 5 |
| 7. Reranking (stage 3) | steps 1–6, and a measured cost curve — the 200× finding says this may not pay |

Steps 1 and 2 are available immediately, need no corpus growth, and are mostly
configuration of plugins the cluster already runs. They give the lexical baseline a number
for the first time — and without a baseline, no later improvement can be claimed.

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

- **Model selection.** Still deliberately undecided; D6 says what evidence would decide it
  and D10 narrows the field, but the corpus does not yet support producing that evidence.
- **Whether reranking pays at all.** Step 6 is gated on a cost curve, not assumed.
- **Generative answering.** This ADR ends at a ranked, gated result set. What consumes it
  is ADR-0033's business.
- **Multilingual parity.** No longer an unmeasured risk — ZHAW measured it on Swiss court
  decisions and found German and English ahead of French and Italian. What is *not*
  settled is what to do about it: whether a per-language model, per-language thresholds, or
  query translation is the answer. D6's per-language reporting is what makes that
  decidable; this ADR does not decide it.
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
- ZHAW, *Can AI bridge Switzerland's legal language gap?* (2026-06) — 165,556 CH Federal
  Supreme Court decisions; 73% top-10 vs 19% for keyword search; the DE/EN vs FR/IT gap
- OpenSearch Search Relevance Workbench, and its hybrid search optimization experiment
- OpenSearch v3 neural sparse models and `multilingual-v1` — D10's coverage caveat
- BGE-M3 (BAAI), SwissBERT / SentenceSwissBERT (ZurichNLP) — D10 candidates
