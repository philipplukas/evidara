/**
 * Citation-graph traversal — the two operations ADR-0033 names as steps 3-4 of
 * the agentic workflow ("walk up", "walk out"). These become MCP tools
 * (`resolve_citation`, `find_citing`); for now they are plain HTTP.
 */

import { Inject, Injectable } from '@nestjs/common';
import { MetricsService } from '../../core/metrics/metrics.service';
import { normalizeCitationText } from './citation-key';
import { resolveAgainstTargets } from './citation-resolution';
import {
  CITATIONS_REPOSITORY,
  type CitationEdge,
  type CitationsRepository,
  type CitationTarget,
} from './citations.repository';

export type ResolveCitationResult = {
  /** The string the caller asked about. */
  query: string;
  /** The canonical key it normalizes to, or null for a fuzzy citation. */
  normalized_reference: string | null;
  resolved: boolean;
  /**
   * Why an unresolved citation is unresolved. The distinctions matter:
   *
   *   `not_normalizable`    — extractor gap: the string names no identifier.
   *   `no_target_in_corpus` — COVERAGE gap: the norm simply is not ingested.
   *   `ambiguous`           — several DIFFERENT documents in the corpus are
   *                           addressable by this key. Short titles are not
   *                           globally unique, so this is a real state and not
   *                           an error.
   *
   * Collapsing them into a bare `resolved: false` is how a graph ends up with
   * silently missing edges.
   */
  unresolved_reason: 'not_normalizable' | 'no_target_in_corpus' | 'ambiguous' | null;
  /**
   * On `ambiguous`, every norm the key could mean — returned UNRANKED and
   * unfiltered so the caller can disambiguate on evidence it has and we do
   * not. On any other outcome this is the resolved target list.
   */
  targets: CitationTarget[];
};

export type FindCitingResult = {
  query: string;
  /** Keys the queried norm is addressable by (a document may carry several). */
  normalized_references: string[];
  citing: CitationEdge[];
  total: number;
};

export type CitationGraphStats = {
  citations_total: number;
  citations_with_key: number;
  citations_resolved: number;
  /** resolved / total, rounded to 4dp. The headline honesty number. */
  resolution_rate: number;
  unresolved_by_type: Record<string, number>;
};

const DEFAULT_CITING_LIMIT = 50;

@Injectable()
export class CitationsService {
  constructor(
    @Inject(CITATIONS_REPOSITORY)
    private readonly repository: CitationsRepository,
    @Inject(MetricsService)
    private readonly metrics: MetricsService,
  ) {}

  /**
   * `resolve_citation` — a citation string (or canonical key) to the norm it
   * points at.
   *
   * Accepts either form: "SR 210", "sr:210". Fuzzy citations resolve to
   * nothing and SAY SO, rather than falling back to a similarity search that
   * would return a plausible wrong norm.
   */
  async resolve(query: string): Promise<ResolveCitationResult> {
    const normalized = normalizeCitationText(query);

    if (!normalized) {
      this.metrics.recordCitationResolution(false, 'not_normalizable');
      return {
        query,
        normalized_reference: null,
        resolved: false,
        unresolved_reason: 'not_normalizable',
        targets: [],
      };
    }

    const targets = await this.repository.findTargetsByKey(normalized);

    // The AMBIGUITY REFUSAL and the coverage-gap distinction both live in
    // `resolveAgainstTargets` — the single rule the projection write path now
    // shares. Re-deciding either of them here is what let the two copies drift
    // (see `citation-resolution.ts`).
    const resolution = resolveAgainstTargets(normalized, targets);

    if (resolution.status === 'unresolved') {
      this.metrics.recordCitationResolution(false, resolution.reason);
      return {
        query,
        normalized_reference: normalized,
        resolved: false,
        unresolved_reason: resolution.reason,
        targets: resolution.candidates,
      };
    }

    this.metrics.recordCitationResolution(true, null);
    return {
      query,
      normalized_reference: normalized,
      resolved: true,
      unresolved_reason: null,
      targets,
    };
  }

  /**
   * `find_citing` — what cites this norm (cases and laws).
   *
   * `query` is either a document id (`doc_...`), or a citation key / string
   * naming the norm ("sr:210", "SR 210"). A document id is first mapped to the
   * keys that document IS, so both spellings of the question converge on the
   * same traversal.
   */
  async findCiting(query: string, limit = DEFAULT_CITING_LIMIT): Promise<FindCitingResult> {
    const isDocumentId = /^doc_[0-9a-z]+$/i.test(query.trim());

    let normalizedReferences: string[] = [];
    let documentId: string | undefined;

    if (isDocumentId) {
      documentId = query.trim();
      const targets = await this.repository.findTargetsByDocumentId(documentId);
      normalizedReferences = targets.map((t) => `${t.identifier_type}:${t.identifier_value}`);
    } else {
      const normalized = normalizeCitationText(query);
      if (normalized) normalizedReferences = [normalized];
      // Also fold in the documents that ARE this norm, so a citation whose
      // edge was denormalized at write time is still found.
      for (const key of normalizedReferences) {
        const targets = await this.repository.findTargetsByKey(key);
        if (targets.length > 0) documentId = targets[0].document_id;
      }
    }

    if (normalizedReferences.length === 0 && !documentId) {
      return { query, normalized_references: [], citing: [], total: 0 };
    }

    const citing = await this.repository.findCitingEdges({
      normalizedReferences,
      documentId,
      limit,
    });

    // A document's own masthead SR number makes it cite itself; a self-edge is
    // not an answer to "what cites this".
    const external = citing.filter((edge) => edge.source_document_id !== documentId);

    return {
      query,
      normalized_references: normalizedReferences,
      citing: external,
      total: external.length,
    };
  }

  /**
   * Corpus-wide citation resolution rate.
   *
   * Exposed on the API (not only as a Prometheus counter) because it is the
   * number that says whether the graph is real. A graph with silently missing
   * edges is worse than no graph, so the miss rate is a first-class result,
   * not a debug detail.
   */
  async getStats(): Promise<CitationGraphStats> {
    const stats = await this.repository.getResolutionStats();
    const rate =
      stats.total === 0 ? 0 : Math.round((stats.resolvable / stats.total) * 10000) / 10000;

    this.metrics.setCitationResolutionRate(rate, stats.total, stats.resolvable);

    return {
      citations_total: stats.total,
      citations_with_key: stats.withNormalizedReference,
      citations_resolved: stats.resolvable,
      resolution_rate: rate,
      unresolved_by_type: stats.unresolvedByType,
    };
  }
}
