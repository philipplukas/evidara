/**
 * Every substantive claim this page makes, in one file, each one carrying the
 * code path that makes it true.
 *
 * ── Why the copy lives here and not inline in the JSX ──
 *
 * This is legal technology. An overclaim on this page is not marketing
 * puffery; it is a false statement about what a system can do, made to people
 * whose professional work depends on the answer. Centralising the copy means
 * a reviewer can audit every claim in one diff, against one evidence column,
 * without reading the layout.
 *
 * RULE FOR CONTRIBUTORS: do not add a claim here without a `evidence` pointer
 * to code that demonstrably does the thing today. "It is on the roadmap",
 * "the issue is open", and "the schema has a field for it" are NOT evidence.
 * A field that exists but is never populated belongs in `NOT_YET`, not in
 * `CAPABILITIES` — see `delegates_to` below for exactly that case.
 *
 * Claim IDs (C1…) are referenced in the PR body for sign-off.
 */

export interface Claim {
  id: string;
  title: string;
  body: string;
  /** Code path that makes this claim true. Verified 2026-07-19. */
  evidence: string;
}

/** The product name and the one-line positioning. */
export const HERO = {
  /** C1 */
  eyebrow: "Legal data infrastructure",
  /**
   * C2. Deliberately describes the platform, not an outcome. Evidara is
   * infrastructure that other things are built on; it is not, today, a
   * research product that answers questions.
   */
  headline: "Law is a graph. Most systems store it as a pile of documents.",
  /**
   * C3. Every noun here maps to something in CAPABILITIES below.
   */
  subhead:
    "Evidara acquires legal texts from official publishers, processes them into a canonical form, and connects them — citation edges, norm hierarchy, and in-force dates — so the structure a legal question actually turns on is queryable instead of implied.",
} as const;

/**
 * What the platform verifiably does today. Each of these was checked against
 * the code on 2026-07-19, not against an issue title or a roadmap.
 */
export const CAPABILITIES: readonly Claim[] = [
  {
    id: "C4",
    title: "Acquisition from official publishers",
    body: "Source blueprints pull from official publishers — among them Fedlex for Swiss federal law, RIS for Austrian law, and EUR-Lex for EU law — through a versioned lifecycle where each source version is acquired, run, and reviewed before it is enabled.",
    evidence:
      "platform-control/src/platform_control/services/provider_registry_factory.py (12 registered providers); hierarchies/source_blueprints.yaml (16 templates enabled: fedlex_sparql, ris_ogd, eur_lex_sparql, deterministic_http, firecrawl)",
  },
  {
    id: "C5",
    title: "Canonical processing",
    body: "Acquired documents are normalised into a single canonical shape — stable identity, revision ordering, sections, and a processing manifest recording how each document was produced.",
    evidence:
      "document-intelligence/src/document_intelligence/pipeline.py:150 ProcessingPipeline.process_event",
  },
  {
    id: "C6",
    title: "A resolved citation graph",
    body: "Citations are not left as strings. They are resolved against canonical identifiers — the SR number for Swiss federal law, CELEX for EU law, ECLI for case law — into traversable edges, so you can ask what cites a statute, not just what mentions its name.",
    evidence:
      "legal-search/api/src/core/opensearch/citation-graph-index.mapping.ts (citations + citation-targets indices); modules/projections/projections.service.ts:1145 resolveCitations (joins on normalized_reference.keyword, so edge direction survives projection order); document-intelligence/.../nlp/citation_extractor.py:515 normalize_citation. Resolution is at norm/statute granularity — bare article references ('Art. 36 BV') are NOT resolved; docs/components/legal-search.md records that as the dominant citation form and a known gap",
  },
  {
    id: "C7",
    title: "Temporal validity",
    body: "Norms carry in-force ranges, not just a publication date, and the norm hierarchy can be queried as of a date. In-force state is four-valued — in force, not yet in force, repealed, or explicitly unknown — so a norm whose end date was never recorded is reported as unknown rather than silently treated as current.",
    evidence:
      "legal-search/api/src/core/opensearch/documents-index.mapping.ts:138 in_force_from/in_force_until (populated at projections.service.ts:260); core/norm-hierarchy/in-force.ts:54 resolveInForceState + :80 inForceExclusionClauses (OpenSearch-level must_not filter, not a post-hoc annotation); modules/norm-hierarchy/norm-hierarchy.service.ts inForceAt, reached via the in_force_at query param. Scope: the norm-hierarchy endpoint — main search takes no as-of date (see C11)",
  },
  {
    id: "C8",
    title: "Modelled norm hierarchy",
    body: "Documents are placed on a ranked hierarchy — constitutional, international, federal, cantonal, municipal — and linked to the levels above them, so it is explicit which instrument outranks which rather than being left to inference.",
    evidence:
      "legal-search/api/src/core/norm-hierarchy/norm-hierarchy.vocabulary.ts:36 NormLevel; core/opensearch/documents-index.mapping.ts:90 level/subordinate_to; projections.service.ts:253 deriveDocumentLevel (subordinate_to populated + tested at projections.service.spec.ts:979)",
  },
  {
    id: "C9",
    title: "Explicit coverage",
    body: "The platform records which sources it holds and which it does not. Knowing the boundary of the corpus is what makes it possible to answer “that instrument is not in here” instead of returning the nearest plausible substitute.",
    evidence:
      "platform-control source blueprint enablement lifecycle (ADR-0030, ADR-0035); seeds/reference/jurisdictions.yaml (2,169 jurisdictions modelled, coverage tracked per blueprint)",
  },
];

/**
 * The honest other half. This section is not a disclaimer bolted on at the
 * end — it is load-bearing product positioning. A platform that is explicit
 * about its boundary is making the same argument in its marketing that it
 * makes in its architecture (ADR-0033: refusing correctly beats answering
 * fluently and wrongly).
 *
 * Anything in this list is a thing we must NOT imply elsewhere on the page.
 */
export const NOT_YET: readonly Claim[] = [
  {
    id: "C10",
    title: "No AI agent answering legal questions",
    body: "There is no assistant here that will answer a legal question. The reasoning layer is deliberately last in the build order — a tool layer over an incomplete corpus produces confident, well-cited, wrong answers, which is worse than no product.",
    evidence:
      "ADR-0033 §4: 'Do not build the MCP server first.' No legal-research MCP server exists.",
  },
  {
    id: "C11",
    title: "Search is keyword-based",
    body: "Retrieval today is BM25 keyword matching. Main search also takes no as-of date: temporal filtering exists on the norm-hierarchy endpoint, not on search, so a search result is not yet checked against the law as it stood on a given date.",
    evidence:
      "legal-search/api/src/modules/search/opensearch.adapter.ts:311 multi_match only; no knn_vector field, no neural query, no ingest pipeline. modules/search/dto/search-query.dto.ts has no in_force_at/as_of param; in_force_at appears on one path only in contracts/api/legal-search.openapi.yaml",
  },
  {
    id: "C12",
    title: "The corpus is small",
    body: "Coverage is deliberately narrow and being deepened one vertical slice at a time. Evidara is not a comprehensive legal database and does not claim to be a substitute for one.",
    evidence:
      "ADR-0033 §5 (vertical slice, ~20–50 documents targeted). No current committed corpus count; the most recent figures in-repo are stale.",
  },
  {
    id: "C13",
    title: "The municipal layer is modelled but not reachable",
    body: "2,110 Swiss municipalities exist as jurisdictions in the platform with no acquisition path behind them. Delegation between levels — which body was actually empowered to act — is modelled in the schema but not yet populated.",
    evidence:
      "seeds/reference/jurisdictions.yaml (2,110 jur_ch_gemeinde_* entries, gemeinde_http enabled: false); contracts/schemas/document.schema.json:104 delegates_to 'UNPOPULATED TODAY'",
  },
  {
    id: "C14",
    title: "No user accounts",
    body: "There is no end-user authentication yet. That is why there is no live demo on this page rather than a login link.",
    evidence:
      "legal-search/frontend has no session/login route; both APIs fail closed on a shared service key (#680). User identity is ADR-0038 (Proposed).",
  },
];

/**
 * C15. The thesis, stated plainly. Grounded in ADR-0033's reasoning about why
 * retrieval alone cannot answer a hierarchy question — not a claim that we
 * have solved it.
 */
export const THESIS = {
  heading: "Why structure, and not just better search",
  body: [
    "The questions that matter in legal work are rarely lookups. Asking whether a city could impose a particular restriction is not answered by finding text similar to the question — it is answered by a delegation clause in a cantonal statute and a proportionality test in the constitution, neither of which shares vocabulary with how anyone would phrase the question.",
    "No amount of retrieval tuning bridges that, because the connection is not a similarity relation. It is a hierarchy relation. Either the system holds the structure — which norm outranks which, which version was in force, which body held the competence — or it guesses and sounds certain either way.",
    "So we are building the structure first. The reasoning layer on top of it is comparatively thin, and it is worth nothing until the layer underneath is real.",
  ],
} as const;

/** C16. What signing up actually gets you. No promises we cannot keep. */
export const WAITLIST = {
  heading: "Follow the build",
  body: "We are building in the open against a single acceptance test: one real question, answered end to end over a corpus assembled through the platform — or refused, correctly, because the governing instrument is not in it. Leave an address and we will write when there is something substantive to show. No newsletter, no drip sequence.",
} as const;
