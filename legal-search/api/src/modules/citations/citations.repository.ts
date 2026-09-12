/**
 * Repository port for citation-graph traversal (ADR-0008: OpenSearch logic
 * lives only in adapters).
 *
 * The graph has two directions, and both are keyed on the canonical
 * `{type}:{value}` reference rather than on `target_document_id`:
 *
 *   forward  — `resolve_citation`: a citation string -> the norm it points to
 *   reverse  — `find_citing`: a norm -> the documents that cite it
 *
 * Keying on the canonical reference is what makes traversal ORDER-INDEPENDENT.
 * `target_document_id` is written onto a citation row only if the cited
 * document happened to already be in the corpus when the citing document was
 * projected. Project the BV after a law that cites it and that edge is missing
 * forever, with no error anywhere — precisely the "silently missing edges"
 * failure ADR-0032 is about. Traversing through the key instead means the edge
 * appears the moment both endpoints exist, in either order.
 */

/** A norm that citations can point at — one row of the `citation-targets` index. */
export type CitationTarget = {
  document_id: string;
  identifier_type: string;
  identifier_value: string;
  title?: string;
  document_type?: string;
  jurisdiction?: string;
  /** Set on PROVISION-level targets (`abbrev_art:BV/36`); absent otherwise. */
  section_id?: string;
  /** In-document anchor for `section_id`, e.g. `art_36`. */
  section_anchor?: string;
};

/** A citation edge — one row of the `citations` index. */
export type CitationEdge = {
  citation_id: string;
  source_document_id: string;
  source_section_id?: string;
  citation_text: string;
  citation_type?: string;
  normalized_reference?: string;
  target_document_id?: string;
  target_title?: string;
};

/** Aggregate counts backing the resolution-rate metric. */
export type CitationResolutionStats = {
  /** Every citation row in the index. */
  total: number;
  /** Rows carrying a canonical key — i.e. a deterministic type DI could normalize. */
  withNormalizedReference: number;
  /** Rows whose canonical key matches a row in `citation-targets` — real edges. */
  resolvable: number;
  /** Unresolved counts per `citation_type`, so the gap is attributable. */
  unresolvedByType: Record<string, number>;
};

export const CITATIONS_REPOSITORY = Symbol('CITATIONS_REPOSITORY');

export interface CitationsRepository {
  /** Look up the norm(s) a canonical key addresses. */
  findTargetsByKey(normalizedReference: string): Promise<CitationTarget[]>;

  /**
   * The batch form, for resolving a whole document's citations in one round
   * trip. Returns EVERY row per key — narrowing is `resolveAgainstTargets`'s
   * job, not a repository's. A key with no rows is absent from the map, which
   * is `no_target_in_corpus`; a key the map never saw because the lookup threw
   * is a different state and is signalled by the call rejecting.
   */
  findTargetsByKeys(normalizedReferences: string[]): Promise<Map<string, CitationTarget[]>>;

  /** The canonical keys a document IS — e.g. the BV is `sr:101`. */
  findTargetsByDocumentId(documentId: string): Promise<CitationTarget[]>;

  /**
   * Citations pointing at any of `normalizedReferences`, plus (union) any
   * citation whose write-time `target_document_id` is `documentId`. The union
   * is what makes the reverse edge robust against both projection orders.
   */
  findCitingEdges(input: {
    normalizedReferences: string[];
    documentId?: string;
    limit: number;
  }): Promise<CitationEdge[]>;

  /** Corpus-wide resolution statistics (the honesty metric). */
  getResolutionStats(): Promise<CitationResolutionStats>;
}
