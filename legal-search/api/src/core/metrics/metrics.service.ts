/**
 * Prometheus counters for the legal-search funnel (ADR-0032).
 *
 * Deliberately dependency-free: adapters inject this and call `recordX()`. The
 * OpenSearch-derived gauges live in `SearchIndexProbe`, so instrumenting a code
 * path never drags an OpenSearch client into it.
 *
 * Counters answer "is work flowing"; the probe gauges answer "did the work land".
 * The outage this exists to catch (#553) was invisible to both liveness probes and
 * logs: every pod was Ready while `documents-read` resolved to nothing.
 */
import { Injectable } from '@nestjs/common';
import { Counter, collectDefaultMetrics, Gauge, Registry } from 'prom-client';

@Injectable()
export class MetricsService {
  readonly registry: Registry;

  /** Every search request that reached the OpenSearch adapter. */
  private readonly searchQueries: Counter;
  /** Searches that came back with `total === 0` (index empty, analyzer broken, bad reindex). */
  private readonly searchZeroHits: Counter;
  /** Searches where the OpenSearch call threw. The adapter swallows these and returns
   *  an empty result, so without this counter a backend outage looks like "no matches". */
  private readonly searchErrors: Counter;
  /** Documents upserted into the write alias by the projection path. */
  private readonly documentsIndexed: Counter;
  /** Documents removed from the write alias (withdrawal projections). */
  private readonly documentsDeleted: Counter;

  // ── Citation graph (#582, ADR-0033) ──
  // An unresolved citation is a BROKEN EDGE. A citation graph with silently
  // missing edges is worse than no graph, because every consumer downstream
  // treats absence of an edge as absence of a relation. These metrics exist so
  // that the miss rate is loud rather than invisible.

  /** Citation-target rows written by projections (the graph's addressable nodes). */
  private readonly citationTargetsIndexed: Counter;
  /** Citations projected, labelled by whether DI produced a canonical key. */
  private readonly citationsProjected: Counter<'keyed'>;
  /** `resolve_citation` calls, labelled by outcome. */
  private readonly citationResolutions: Counter<'outcome'>;
  /** Corpus-wide share of citations that resolve to a real edge (0..1). */
  private readonly citationResolutionRate: Gauge;
  /** Corpus-wide citation counts behind the rate, so alerts can require a floor. */
  private readonly citationsTotal: Gauge;
  private readonly citationsResolvedTotal: Gauge;

  constructor() {
    this.registry = new Registry();
    this.registry.setDefaultLabels({ service: 'legal-search-api' });
    collectDefaultMetrics({ register: this.registry });

    this.searchQueries = new Counter({
      name: 'legal_search_search_queries_total',
      help: 'Search queries executed against OpenSearch.',
      registers: [this.registry],
    });
    this.searchZeroHits = new Counter({
      name: 'legal_search_search_queries_zero_hits_total',
      help: 'Search queries that returned zero hits.',
      registers: [this.registry],
    });
    this.searchErrors = new Counter({
      name: 'legal_search_search_errors_total',
      help: 'Search queries where the OpenSearch call failed (degraded to an empty result).',
      registers: [this.registry],
    });
    this.documentsIndexed = new Counter({
      name: 'legal_search_documents_indexed_total',
      help: 'Documents upserted into the OpenSearch write alias by projections.',
      registers: [this.registry],
    });
    this.documentsDeleted = new Counter({
      name: 'legal_search_documents_deleted_total',
      help: 'Documents deleted from the OpenSearch write alias by withdrawal projections.',
      registers: [this.registry],
    });

    this.citationTargetsIndexed = new Counter({
      name: 'legal_search_citation_targets_indexed_total',
      help: 'Citation-target rows (norm identifiers) written to the citation-targets index.',
      registers: [this.registry],
    });
    this.citationsProjected = new Counter({
      name: 'legal_search_citations_projected_total',
      help: 'Citations projected, labelled by whether DI produced a canonical key (keyed=true|false). keyed=false is an extractor gap: the citation can never become an edge.',
      labelNames: ['keyed'],
      registers: [this.registry],
    });
    this.citationResolutions = new Counter({
      name: 'legal_search_citation_resolutions_total',
      help: 'resolve_citation calls by outcome: resolved | not_normalizable (fuzzy citation type) | no_target_in_corpus (key is valid but the norm is not ingested — a coverage gap).',
      labelNames: ['outcome'],
      registers: [this.registry],
    });
    this.citationResolutionRate = new Gauge({
      name: 'legal_search_citation_resolution_rate',
      help: 'Share of citations in the corpus that resolve to a citation-target (0..1). The citation graph edge coverage.',
      registers: [this.registry],
    });
    this.citationsTotal = new Gauge({
      name: 'legal_search_citations_indexed_count',
      help: 'Citations in the citations index (the denominator of the resolution rate).',
      registers: [this.registry],
    });
    this.citationsResolvedTotal = new Gauge({
      name: 'legal_search_citations_resolved_count',
      help: 'Citations resolving to a citation-target (the numerator of the resolution rate).',
      registers: [this.registry],
    });
  }

  recordSearch(totalHits: number): void {
    this.searchQueries.inc();
    if (totalHits === 0) {
      this.searchZeroHits.inc();
    }
  }

  recordSearchError(): void {
    this.searchQueries.inc();
    this.searchZeroHits.inc();
    this.searchErrors.inc();
  }

  recordDocumentIndexed(): void {
    this.documentsIndexed.inc();
  }

  recordDocumentDeleted(): void {
    this.documentsDeleted.inc();
  }

  /** Citation-target rows written by a projection. */
  recordCitationTargetsIndexed(count: number): void {
    if (count > 0) this.citationTargetsIndexed.inc(count);
  }

  /**
   * Citations projected for one document, split by whether DI could produce a
   * canonical key. `keyed=false` citations are permanently un-edgeable with
   * today's extractor — counting them is how that gap stays visible.
   */
  recordCitationsProjected(keyed: number, unkeyed: number): void {
    if (keyed > 0) this.citationsProjected.inc({ keyed: 'true' }, keyed);
    if (unkeyed > 0) this.citationsProjected.inc({ keyed: 'false' }, unkeyed);
  }

  /** One `resolve_citation` outcome. */
  recordCitationResolution(
    resolved: boolean,
    reason: 'not_normalizable' | 'no_target_in_corpus' | 'ambiguous' | null,
  ): void {
    this.citationResolutions.inc({ outcome: resolved ? 'resolved' : (reason ?? 'unresolved') });
  }

  /** Corpus-wide resolution rate, refreshed whenever the stats endpoint runs. */
  setCitationResolutionRate(rate: number, total: number, resolved: number): void {
    this.citationResolutionRate.set(rate);
    this.citationsTotal.set(total);
    this.citationsResolvedTotal.set(resolved);
  }
}
