/**
 * OpenSearch adapter for citation-graph traversal (ADR-0008).
 *
 * Query-shape note: every term filter targets the `.keyword` sub-field. The
 * live `citations` index was created by dynamic mapping (string -> `text` +
 * `.keyword`), while the managed mappings in `citation-graph-index.mapping.ts`
 * declare `keyword` WITH a `.keyword` sub-field. `.keyword` is therefore the
 * one form that resolves against both, so traversal works on the existing
 * cluster and on a freshly bootstrapped one without a reindex.
 */

import { Inject, Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import type { Client } from '@opensearch-project/opensearch';
import { OPENSEARCH_CLIENT } from '../../core/opensearch/client';
import { parseCitationKey } from './citation-key';
import type {
  CitationEdge,
  CitationResolutionStats,
  CitationsRepository,
  CitationTarget,
} from './citations.repository';

type OpenSearchHit = { _source?: Record<string, unknown> };

@Injectable()
export class CitationsOpenSearchAdapter implements CitationsRepository {
  private readonly logger = new Logger(CitationsOpenSearchAdapter.name);
  private readonly indexCitations: string;
  private readonly indexCitationTargets: string;

  constructor(
    @Inject(OPENSEARCH_CLIENT)
    private readonly client: Client,
    @Inject(ConfigService)
    config: ConfigService,
  ) {
    this.indexCitations = config.get<string>('opensearch.citationsIndex') ?? 'citations';
    this.indexCitationTargets =
      config.get<string>('opensearch.citationTargetsIndex') ?? 'citation-targets';
  }

  private static toTarget(src: Record<string, unknown>): CitationTarget {
    return {
      document_id: src.document_id as string,
      identifier_type: src.identifier_type as string,
      identifier_value: src.identifier_value as string,
      title: src.title as string | undefined,
      document_type: src.document_type as string | undefined,
      jurisdiction: src.jurisdiction as string | undefined,
      section_id: src.section_id as string | undefined,
      section_anchor: src.section_anchor as string | undefined,
    };
  }

  private static toEdge(src: Record<string, unknown>): CitationEdge {
    return {
      citation_id: src.citation_id as string,
      source_document_id: src.source_document_id as string,
      source_section_id: src.source_section_id as string | undefined,
      citation_text: src.citation_text as string,
      citation_type: src.citation_type as string | undefined,
      normalized_reference: src.normalized_reference as string | undefined,
      target_document_id: src.target_document_id as string | undefined,
      target_title: src.target_title as string | undefined,
    };
  }

  async findTargetsByKey(normalizedReference: string): Promise<CitationTarget[]> {
    const parsed = parseCitationKey(normalizedReference);
    if (!parsed) return [];

    try {
      const response = await this.client.search({
        index: this.indexCitationTargets,
        body: {
          size: 10,
          query: {
            bool: {
              filter: [
                { term: { 'identifier_type.keyword': parsed.identifierType } },
                { term: { 'identifier_value.keyword': parsed.identifierValue } },
              ],
            },
          },
        },
      });
      return (response.body.hits?.hits ?? [])
        .filter((hit: OpenSearchHit) => hit._source != null)
        .map((hit: OpenSearchHit) =>
          CitationsOpenSearchAdapter.toTarget(hit._source as Record<string, unknown>),
        );
    } catch (err) {
      // An absent index means an empty graph, not an outage — but it is exactly
      // the state that made the graph invisible, so warn rather than swallow.
      this.logger.warn(`find_targets_by_key_failed: ${normalizedReference}`, err as Error);
      return [];
    }
  }

  async findTargetsByDocumentId(documentId: string): Promise<CitationTarget[]> {
    try {
      const response = await this.client.search({
        index: this.indexCitationTargets,
        body: {
          size: 20,
          query: { term: { 'document_id.keyword': documentId } },
        },
      });
      return (response.body.hits?.hits ?? [])
        .filter((hit: OpenSearchHit) => hit._source != null)
        .map((hit: OpenSearchHit) =>
          CitationsOpenSearchAdapter.toTarget(hit._source as Record<string, unknown>),
        );
    } catch (err) {
      this.logger.warn(`find_targets_by_document_failed: ${documentId}`, err as Error);
      return [];
    }
  }

  async findCitingEdges(input: {
    normalizedReferences: string[];
    documentId?: string;
    limit: number;
  }): Promise<CitationEdge[]> {
    const should: Array<Record<string, unknown>> = [];
    if (input.normalizedReferences.length > 0) {
      should.push({
        terms: { 'normalized_reference.keyword': input.normalizedReferences },
      });
    }
    if (input.documentId) {
      should.push({ term: { 'target_document_id.keyword': input.documentId } });
    }
    if (should.length === 0) return [];

    try {
      const response = await this.client.search({
        index: this.indexCitations,
        body: {
          size: input.limit,
          query: { bool: { should, minimum_should_match: 1 } },
        },
      });
      return (response.body.hits?.hits ?? [])
        .filter((hit: OpenSearchHit) => hit._source != null)
        .map((hit: OpenSearchHit) =>
          CitationsOpenSearchAdapter.toEdge(hit._source as Record<string, unknown>),
        );
    } catch (err) {
      this.logger.warn('find_citing_edges_failed', err as Error);
      return [];
    }
  }

  async getResolutionStats(): Promise<CitationResolutionStats> {
    const empty: CitationResolutionStats = {
      total: 0,
      withNormalizedReference: 0,
      resolvable: 0,
      unresolvedByType: {},
    };

    try {
      // Every canonical key that IS in the corpus. The target index is small by
      // construction (one row per identifier a document carries), so pulling
      // the key set and intersecting in-process avoids a cross-index join that
      // OpenSearch cannot do natively.
      const targetKeys = await this.loadAllTargetKeys();

      const response = await this.client.search({
        index: this.indexCitations,
        body: {
          size: 0,
          track_total_hits: true,
          query: { match_all: {} },
          aggs: {
            with_key: {
              filter: { exists: { field: 'normalized_reference' } },
              aggs: {
                by_key: { terms: { field: 'normalized_reference.keyword', size: 10000 } },
              },
            },
            by_type: { terms: { field: 'citation_type.keyword', size: 100 } },
            unresolved_by_type: {
              filter: {
                bool: { must_not: [{ exists: { field: 'normalized_reference' } }] },
              },
              aggs: {
                by_type: { terms: { field: 'citation_type.keyword', size: 100 } },
              },
            },
          },
        },
      });

      const total =
        typeof response.body.hits?.total === 'object'
          ? (response.body.hits.total as { value: number }).value
          : ((response.body.hits?.total as number) ?? 0);

      // biome-ignore lint/suspicious/noExplicitAny: OpenSearch agg types are loose
      const aggs = response.body.aggregations as Record<string, any> | undefined;

      const withNormalizedReference = (aggs?.with_key?.doc_count as number) ?? 0;

      const keyBuckets = (aggs?.with_key?.by_key?.buckets ?? []) as Array<{
        key: string;
        doc_count: number;
      }>;

      let resolvable = 0;
      const unresolvedByType: Record<string, number> = {};
      // Keys that exist but address nothing in the corpus: a dangling edge.
      // Attributed to `unresolved_target` so it is distinguishable from a
      // citation DI could not normalize at all.
      let danglingKeyed = 0;
      for (const bucket of keyBuckets) {
        if (targetKeys.has(bucket.key)) {
          resolvable += bucket.doc_count;
        } else {
          danglingKeyed += bucket.doc_count;
        }
      }
      if (danglingKeyed > 0) unresolvedByType.unresolved_target = danglingKeyed;

      // Citations DI could not normalize at all (fuzzy types), by type — this
      // is the list that tells us which extractor to teach next.
      const unresolvedBuckets = (aggs?.unresolved_by_type?.by_type?.buckets ?? []) as Array<{
        key: string;
        doc_count: number;
      }>;
      for (const bucket of unresolvedBuckets) {
        unresolvedByType[bucket.key] = (unresolvedByType[bucket.key] ?? 0) + bucket.doc_count;
      }

      return { total, withNormalizedReference, resolvable, unresolvedByType };
    } catch (err) {
      this.logger.warn('citation_resolution_stats_failed', err as Error);
      return empty;
    }
  }

  /** All `{type}:{value}` keys present in `citation-targets`. */
  private async loadAllTargetKeys(): Promise<Set<string>> {
    const keys = new Set<string>();
    try {
      const response = await this.client.search({
        index: this.indexCitationTargets,
        body: {
          size: 0,
          aggs: {
            by_type: {
              terms: { field: 'identifier_type.keyword', size: 50 },
              aggs: {
                by_value: { terms: { field: 'identifier_value.keyword', size: 10000 } },
              },
            },
          },
        },
      });
      // biome-ignore lint/suspicious/noExplicitAny: OpenSearch agg types are loose
      const aggs = response.body.aggregations as Record<string, any> | undefined;
      const typeBuckets = (aggs?.by_type?.buckets ?? []) as Array<{
        key: string;
        by_value?: { buckets?: Array<{ key: string }> };
      }>;
      for (const typeBucket of typeBuckets) {
        for (const valueBucket of typeBucket.by_value?.buckets ?? []) {
          keys.add(`${typeBucket.key}:${valueBucket.key}`);
        }
      }
    } catch (err) {
      this.logger.warn('load_target_keys_failed', err as Error);
    }
    return keys;
  }
}
