import { Inject, Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import type { Client } from '@opensearch-project/opensearch';
import { MetricsService } from '../../core/metrics/metrics.service';
import { OPENSEARCH_CLIENT } from '../../core/opensearch/client';
import type { CitationTarget } from '../citations/citations.repository';
import type {
  CitationProjection,
  CitationTargetCandidates,
  CitationTargetEntry,
  IndexedDocumentEntry,
  IndexedDocumentPage,
  IndexedDocumentQuery,
  ProjectionHistoryEntry,
  ProjectionHistoryPage,
  ProjectionHistoryQuery,
  ProjectionHistoryStats,
  ProjectionRepository,
  SearchProjectionDocument,
  SectionProjection,
} from './projections.repository';

@Injectable()
export class ProjectionOpenSearchAdapter implements ProjectionRepository {
  private readonly logger = new Logger(ProjectionOpenSearchAdapter.name);

  /**
   * Rows per key to fetch when resolving. One document legitimately publishes
   * several rows for a key (statute + article section); several documents
   * publishing the same key is ambiguity. Both need headroom above 1.
   */
  private static readonly MAX_TARGET_ROWS_PER_KEY = 10;
  /** Hard ceiling on one resolution page, so a pathological key cannot page the index. */
  private static readonly MAX_TARGET_ROWS = 1000;

  private readonly indexDocumentsWrite: string;
  private readonly indexSections: string;
  private readonly indexCitations: string;
  private readonly indexCitationTargets: string;
  private readonly indexProjectionHistory: string;

  private static readonly DEFAULT_INDEXED_PAGE_SIZE = 500;
  private static readonly MAX_INDEXED_PAGE_SIZE = 1000;

  constructor(
    @Inject(OPENSEARCH_CLIENT)
    private readonly client: Client,
    @Inject(ConfigService)
    config: ConfigService,
    @Inject(MetricsService)
    private readonly metrics: MetricsService,
  ) {
    this.indexDocumentsWrite =
      config.get<string>('opensearch.documentsWriteAlias') ?? 'documents-write';
    this.indexSections = config.get<string>('opensearch.sectionsIndex') ?? 'sections';
    this.indexCitations = config.get<string>('opensearch.citationsIndex') ?? 'citations';
    this.indexCitationTargets =
      config.get<string>('opensearch.citationTargetsIndex') ?? 'citation-targets';
    this.indexProjectionHistory =
      config.get<string>('opensearch.projectionHistoryIndex') ?? 'projection-history';
  }

  async hasHistoryEvent(eventId: string): Promise<boolean> {
    try {
      const result = await this.client.exists({
        index: this.indexProjectionHistory,
        id: eventId,
      });
      return Boolean(result.body);
    } catch {
      return false;
    }
  }

  async getLatestRevision(documentId: string): Promise<number | null> {
    try {
      const response = await this.client.search({
        index: this.indexProjectionHistory,
        body: {
          size: 1,
          query: {
            term: { 'document_id.keyword': documentId },
          },
          sort: [{ document_revision: { order: 'desc' } }],
        },
      });
      const hit = response.body.hits?.hits?.[0]?._source as
        | { document_revision?: number }
        | undefined;
      return typeof hit?.document_revision === 'number' ? hit.document_revision : null;
    } catch (err) {
      this.logger.warn(`Failed to read latest revision for ${documentId}`, err as Error);
      return null;
    }
  }

  /**
   * Walk the write alias in `document_id` order so a reconcile pass can diff the
   * derived index against canonical Delta.
   *
   * `search_after` rather than `from`/`size`: deep paging past `index.max_result_window`
   * (10k by default) silently 400s, and an enumeration that stops early would report
   * every document past the cutoff as absent from the index — the opposite of the truth.
   *
   * `commentary_insight` rows are excluded. Their `document_id` is an `ins_*` insight id
   * with no `published_documents` row behind it, so a canonical diff would classify every
   * one of them as an orphan and a reconcile pass would delete the lot. Rows written
   * before `record_kind` existed carry no such field and are legal documents, which is
   * why this is a `must_not` on commentary rather than a `must` on legal_document.
   */
  async listIndexedDocuments(query: IndexedDocumentQuery): Promise<IndexedDocumentPage> {
    const limit = Math.min(
      Math.max(query.limit ?? ProjectionOpenSearchAdapter.DEFAULT_INDEXED_PAGE_SIZE, 1),
      ProjectionOpenSearchAdapter.MAX_INDEXED_PAGE_SIZE,
    );

    const body: Record<string, unknown> = {
      size: limit,
      sort: [{ document_id: { order: 'asc' } }],
      _source: [
        'document_id',
        'document_revision',
        'processing_manifest_id',
        'source_id',
        'source_version_id',
        'run_id',
        'title',
      ],
      query: {
        bool: { must_not: [{ term: { record_kind: 'commentary_insight' } }] },
      },
    };
    if (query.after) {
      body.search_after = [query.after];
    }

    const runSearch = () => this.client.search({ index: this.indexDocumentsWrite, body });
    let response: Awaited<ReturnType<typeof runSearch>>;
    try {
      response = await runSearch();
    } catch (err) {
      const message = String((err as { message?: string }).message ?? '');
      // An absent index means nothing is indexed, which is a complete and honest
      // answer. Every other failure must surface: a caller that treats a failed
      // enumeration as "the index is empty" would conclude nothing is orphaned.
      if (message.includes('index_not_found_exception')) {
        return { data: [], limit };
      }
      throw err;
    }

    const hits = (response.body.hits?.hits ?? []) as Array<{
      _source: Record<string, unknown>;
    }>;
    const data: IndexedDocumentEntry[] = [];
    for (const hit of hits) {
      const src = hit._source ?? {};
      const documentId = typeof src.document_id === 'string' ? src.document_id : undefined;
      if (!documentId) continue;
      data.push({
        document_id: documentId,
        document_revision:
          typeof src.document_revision === 'number' ? src.document_revision : undefined,
        processing_manifest_id:
          typeof src.processing_manifest_id === 'string' ? src.processing_manifest_id : undefined,
        source_id: typeof src.source_id === 'string' ? src.source_id : undefined,
        source_version_id:
          typeof src.source_version_id === 'string' ? src.source_version_id : undefined,
        run_id: typeof src.run_id === 'string' ? src.run_id : undefined,
        title: typeof src.title === 'string' ? src.title : undefined,
      });
    }

    // A short page is the last page. Only a full page can have more behind it.
    const nextAfter = hits.length === limit ? data.at(-1)?.document_id : undefined;
    return nextAfter ? { data, limit, next_after: nextAfter } : { data, limit };
  }

  async upsertProjection(document: SearchProjectionDocument): Promise<void> {
    await this.client.index({
      index: this.indexDocumentsWrite,
      id: document.document_id,
      body: document,
      refresh: 'wait_for',
    });
    // Counted only after the write succeeds: this is the funnel's "docs reached
    // OpenSearch" stage, and it must not count attempts.
    this.metrics.recordDocumentIndexed();
  }

  async deleteProjection(documentId: string): Promise<void> {
    try {
      await this.client.delete({
        index: this.indexDocumentsWrite,
        id: documentId,
        refresh: 'wait_for',
      });
      this.metrics.recordDocumentDeleted();
    } catch (err) {
      // Ignore missing index/document errors to keep event handling idempotent.
      const message = String((err as { message?: string }).message ?? '');
      if (message.includes('index_not_found_exception') || message.includes('not_found')) {
        return;
      }
      throw err;
    }
  }

  async bulkIndexSections(sections: SectionProjection[]): Promise<void> {
    if (sections.length === 0) return;
    const body = sections.flatMap((section) => [
      { index: { _index: this.indexSections, _id: section.section_id } },
      section,
    ]);
    try {
      const response = await this.client.bulk({ body, refresh: 'wait_for' });
      if (response.body.errors) {
        const failed = (response.body.items as Array<{ index?: { error?: unknown } }>).filter(
          (item) => item.index?.error,
        );
        this.logger.warn(`bulk_index_sections_partial_failure`, {
          total: sections.length,
          failed: failed.length,
        });
      }
    } catch (err) {
      this.logger.error('bulk_index_sections_failed', err as Error);
    }
  }

  async bulkIndexCitations(citations: CitationProjection[]): Promise<void> {
    if (citations.length === 0) return;
    const body = citations.flatMap((citation) => [
      { index: { _index: this.indexCitations, _id: citation.citation_id } },
      citation,
    ]);
    try {
      const response = await this.client.bulk({ body, refresh: 'wait_for' });
      if (response.body.errors) {
        const failed = (response.body.items as Array<{ index?: { error?: unknown } }>).filter(
          (item) => item.index?.error,
        );
        this.logger.warn(`bulk_index_citations_partial_failure`, {
          total: citations.length,
          failed: failed.length,
        });
      }
      // Counted after the write, like `recordDocumentIndexed`. A citation with
      // no `normalized_reference` is one DI could not normalize — it can never
      // become an edge, so it is counted separately rather than blended into a
      // single "citations indexed" number that would look healthy.
      const keyed = citations.filter((c) => Boolean(c.normalized_reference)).length;
      this.metrics.recordCitationsProjected(keyed, citations.length - keyed);
    } catch (err) {
      this.logger.error('bulk_index_citations_failed', err as Error);
    }
  }

  /**
   * The `_id` a citation target is written under.
   *
   * For the deterministic identifier types the id stays `{type}:{value}`, so
   * re-projecting a document is idempotent.
   *
   * For `abbrev` / `abbrev_art` the document id is appended, because short
   * titles are NOT globally unique — a cantonal and a federal act can both be
   * abbreviated `EG`, and the BV's own `title_short` differs per language.
   * Under a bare `{type}:{value}` id those rows would silently overwrite each
   * other and the last writer would win, which is precisely the silent
   * disambiguation #594 must not do. Keeping them as separate rows lets
   * `findTargetsByKey` return BOTH, and the resolver refuse as `ambiguous`.
   */
  private static citationTargetId(target: CitationTargetEntry): string {
    const key = `${target.identifier_type}:${target.identifier_value}`;
    if (target.identifier_type !== 'abbrev' && target.identifier_type !== 'abbrev_art') {
      return key;
    }
    return target.section_id
      ? `${key}#${target.document_id}#${target.section_id}`
      : `${key}#${target.document_id}`;
  }

  async bulkIndexCitationTargets(targets: CitationTargetEntry[]): Promise<void> {
    if (targets.length === 0) return;
    const body = targets.flatMap((target) => [
      {
        index: {
          _index: this.indexCitationTargets,
          _id: ProjectionOpenSearchAdapter.citationTargetId(target),
        },
      },
      target,
    ]);
    try {
      const response = await this.client.bulk({ body, refresh: 'wait_for' });
      if (response.body.errors) {
        const failed = (response.body.items as Array<{ index?: { error?: unknown } }>).filter(
          (item) => item.index?.error,
        );
        this.logger.warn(`bulk_index_citation_targets_partial_failure`, {
          total: targets.length,
          failed: failed.length,
        });
      }
      this.metrics.recordCitationTargetsIndexed(targets.length);
    } catch (err) {
      this.logger.error('bulk_index_citation_targets_failed', err as Error);
    }
  }

  async deleteSectionsForDocument(documentId: string): Promise<void> {
    try {
      await this.client.deleteByQuery({
        index: this.indexSections,
        body: { query: { term: { document_id: documentId } } },
        refresh: true,
      });
    } catch (err) {
      const message = String((err as { message?: string }).message ?? '');
      if (message.includes('index_not_found_exception')) return;
      this.logger.warn(`delete_sections_for_document_failed`, err as Error);
    }
  }

  async deleteCitationsForDocument(documentId: string): Promise<void> {
    try {
      await this.client.deleteByQuery({
        index: this.indexCitations,
        body: { query: { term: { source_document_id: documentId } } },
        refresh: true,
      });
    } catch (err) {
      const message = String((err as { message?: string }).message ?? '');
      if (message.includes('index_not_found_exception')) return;
      this.logger.warn(`delete_citations_for_document_failed`, err as Error);
    }
  }

  async appendHistory(entry: ProjectionHistoryEntry): Promise<void> {
    try {
      await this.client.create({
        index: this.indexProjectionHistory,
        id: entry.eventId,
        body: {
          event_id: entry.eventId,
          event_type: entry.eventType,
          document_id: entry.documentId,
          document_revision: entry.documentRevision,
          processing_manifest_id: entry.processingManifestId,
          run_id: entry.runId,
          occurred_at: entry.occurredAt,
          status: entry.status,
          notes: entry.notes,
        },
        refresh: 'wait_for',
      });
    } catch (err) {
      const message = String((err as { message?: string }).message ?? '');
      if (message.includes('version_conflict_engine_exception')) {
        return;
      }
      throw err;
    }
  }

  async queryHistory(query: ProjectionHistoryQuery): Promise<ProjectionHistoryPage> {
    const limit = query.limit ?? 50;
    const offset = query.offset ?? 0;
    const filters: Array<Record<string, unknown>> = [];

    if (query.documentId) {
      filters.push({ term: { 'document_id.keyword': query.documentId } });
    }
    if (query.runId) {
      filters.push({ term: { 'run_id.keyword': query.runId } });
    }
    if (query.status) {
      filters.push({ term: { 'status.keyword': query.status } });
    }

    const body: Record<string, unknown> = {
      size: limit,
      from: offset,
      sort: [{ occurred_at: { order: 'desc' } }],
      track_total_hits: true,
    };

    if (filters.length > 0) {
      body.query = { bool: { filter: filters } };
    } else {
      body.query = { match_all: {} };
    }

    try {
      const response = await this.client.search({
        index: this.indexProjectionHistory,
        body,
      });

      const hits = response.body.hits?.hits ?? [];
      const total =
        typeof response.body.hits?.total === 'object'
          ? (response.body.hits.total as { value: number }).value
          : ((response.body.hits?.total as number) ?? 0);

      const data: ProjectionHistoryEntry[] = (
        hits as Array<{ _source: Record<string, unknown> }>
      ).map((hit) => ({
        eventId: hit._source.event_id as string,
        eventType: hit._source.event_type as ProjectionHistoryEntry['eventType'],
        documentId: hit._source.document_id as string,
        documentRevision: hit._source.document_revision as number,
        processingManifestId: hit._source.processing_manifest_id as string,
        runId: hit._source.run_id as string,
        occurredAt: hit._source.occurred_at as string,
        status: hit._source.status as ProjectionHistoryEntry['status'],
        notes: hit._source.notes as string | undefined,
      }));

      return { data, total, limit, offset };
    } catch (err) {
      this.logger.warn('Failed to query projection history', err as Error);
      return { data: [], total: 0, limit, offset };
    }
  }

  async getHistoryStats(): Promise<ProjectionHistoryStats> {
    try {
      const response = await this.client.search({
        index: this.indexProjectionHistory,
        body: {
          size: 0,
          track_total_hits: true,
          aggs: {
            by_status: {
              terms: { field: 'status.keyword', size: 10 },
            },
            unique_documents: {
              cardinality: { field: 'document_id.keyword' },
            },
          },
        },
      });

      const totalEvents =
        typeof response.body.hits?.total === 'object'
          ? (response.body.hits.total as { value: number }).value
          : ((response.body.hits?.total as number) ?? 0);

      // biome-ignore lint/suspicious/noExplicitAny: OpenSearch agg types are loose
      const aggs = response.body.aggregations as Record<string, any> | undefined;

      const statusBuckets = (aggs?.by_status?.buckets ?? []) as Array<{
        key: string;
        doc_count: number;
      }>;

      const statusCounts: Record<string, number> = {};
      for (const bucket of statusBuckets) {
        statusCounts[bucket.key] = bucket.doc_count;
      }

      const uniqueDocuments = (aggs?.unique_documents?.value as number) ?? 0;

      return {
        totalEvents,
        applied: statusCounts.applied ?? 0,
        stale: statusCounts.stale ?? 0,
        ignoredDuplicate: statusCounts.ignored_duplicate ?? 0,
        uniqueDocuments,
      };
    } catch (err) {
      this.logger.warn('Failed to get projection history stats', err as Error);
      return {
        totalEvents: 0,
        applied: 0,
        stale: 0,
        ignoredDuplicate: 0,
        uniqueDocuments: 0,
      };
    }
  }

  /**
   * Every `citation-targets` row matching each key, grouped by key.
   *
   * This adapter deliberately does NOT choose among them. It used to build a
   * `Map<key, match>` and let the last search hit win, which silently turned an
   * ambiguous key into one arbitrary resolved edge. Narrowing is the resolution
   * decision and lives in `resolveAgainstTargets`.
   */
  async resolveCitationTargets(normalizedRefs: string[]): Promise<CitationTargetCandidates> {
    const result: CitationTargetCandidates = new Map();
    if (normalizedRefs.length === 0) return result;

    const shouldClauses = normalizedRefs.map((ref) => {
      const colonIdx = ref.indexOf(':');
      const identifierType = colonIdx > 0 ? ref.slice(0, colonIdx) : ref;
      const identifierValue = colonIdx > 0 ? ref.slice(colonIdx + 1) : '';
      return {
        bool: {
          filter: [
            { term: { 'identifier_type.keyword': identifierType } },
            { term: { 'identifier_value.keyword': identifierValue } },
          ],
        },
      };
    });

    try {
      const response = await this.client.search({
        index: this.indexCitationTargets,
        body: {
          // One hit per key is NOT enough. Ambiguity is "several documents
          // answer this key", so a page sized to the number of keys truncates
          // exactly the rival rows the refusal is computed from — turning an
          // ambiguous key into a confident single match by page size alone.
          size: Math.min(
            normalizedRefs.length * ProjectionOpenSearchAdapter.MAX_TARGET_ROWS_PER_KEY,
            ProjectionOpenSearchAdapter.MAX_TARGET_ROWS,
          ),
          query: {
            bool: { should: shouldClauses, minimum_should_match: 1 },
          },
        },
      });

      const hits = (response.body.hits?.hits ?? []) as Array<{
        _source: Record<string, unknown>;
      }>;

      for (const hit of hits) {
        const src = hit._source;
        const idType = src.identifier_type as string | undefined;
        const idValue = src.identifier_value as string | undefined;
        if (!idType || idValue === undefined) continue;
        const normalizedRef = `${idType}:${idValue}`;
        if (!normalizedRefs.includes(normalizedRef)) continue;

        const target: CitationTarget = {
          document_id: src.document_id as string,
          identifier_type: idType,
          identifier_value: idValue,
          title: src.title as string | undefined,
          document_type: src.document_type as string | undefined,
          jurisdiction: src.jurisdiction as string | undefined,
          section_id: src.section_id as string | undefined,
          section_anchor: src.section_anchor as string | undefined,
        };
        const existing = result.get(normalizedRef);
        if (existing) existing.push(target);
        else result.set(normalizedRef, [target]);
      }
    } catch (err) {
      this.logger.warn('Failed to resolve citation targets', err as Error);
    }

    return result;
  }
}
