import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MetricsService } from '../../core/metrics/metrics.service';
import type { CitationEdge, CitationsRepository, CitationTarget } from './citations.repository';
import { CitationsService } from './citations.service';

/**
 * The BV is `sr:101`, the ZGB is `sr:210`. The golden Fedlex fixture
 * (`document-intelligence/tests/golden/ch_fedlex_law_html/`) is a BV that cites
 * the ZGB — so "the BV cites SR 210" is the smallest real edge in the corpus,
 * and it is the one these tests walk in both directions.
 */
const BV: CitationTarget = {
  document_id: 'doc_bv',
  identifier_type: 'sr',
  identifier_value: '101',
  title: 'Bundesverfassung der Schweizerischen Eidgenossenschaft',
  document_type: 'law',
  jurisdiction: 'CH',
};

const ZGB: CitationTarget = {
  document_id: 'doc_zgb',
  identifier_type: 'sr',
  identifier_value: '210',
  title: 'Schweizerisches Zivilgesetzbuch',
  document_type: 'law',
  jurisdiction: 'CH',
};

/** The BV's citation of the ZGB — "Ergaenzend gilt das ZGB (SR 210)." */
const BV_CITES_ZGB: CitationEdge = {
  citation_id: 'cit_1',
  source_document_id: 'doc_bv',
  source_section_id: 'sec_3',
  citation_text: 'SR 210',
  citation_type: 'sr',
  normalized_reference: 'sr:210',
  // Deliberately absent: the ZGB had not been projected when the BV was, so the
  // write-time denormalization never happened. Traversal must still find it.
  target_document_id: undefined,
};

function createRepositoryMock(): CitationsRepository {
  return {
    findTargetsByKey: vi.fn().mockResolvedValue([]),
    findTargetsByDocumentId: vi.fn().mockResolvedValue([]),
    findCitingEdges: vi.fn().mockResolvedValue([]),
    getResolutionStats: vi.fn().mockResolvedValue({
      total: 0,
      withNormalizedReference: 0,
      resolvable: 0,
      unresolvedByType: {},
    }),
  };
}

describe('CitationsService', () => {
  let repository: CitationsRepository;
  let metrics: MetricsService;
  let service: CitationsService;

  beforeEach(() => {
    repository = createRepositoryMock();
    metrics = new MetricsService();
    service = new CitationsService(repository, metrics);
  });

  describe('resolve_citation', () => {
    it('resolves a citation string to the norm it points at', async () => {
      (repository.findTargetsByKey as ReturnType<typeof vi.fn>).mockResolvedValue([ZGB]);

      const result = await service.resolve('SR 210');

      expect(repository.findTargetsByKey).toHaveBeenCalledWith('sr:210');
      expect(result).toMatchObject({
        query: 'SR 210',
        normalized_reference: 'sr:210',
        resolved: true,
        unresolved_reason: null,
      });
      expect(result.targets).toEqual([ZGB]);
      // The whole point: the string "SR 210" landed on the ZGB, not on something
      // that merely looks similar.
      expect(result.targets[0].document_id).toBe('doc_zgb');
    });

    it('resolves a canonical key just as well as prose', async () => {
      (repository.findTargetsByKey as ReturnType<typeof vi.fn>).mockResolvedValue([ZGB]);

      const result = await service.resolve('sr:210');

      expect(result.resolved).toBe(true);
      expect(result.targets[0].document_id).toBe('doc_zgb');
    });

    it('reports a fuzzy citation as not_normalizable rather than guessing', async () => {
      const result = await service.resolve('Art. 36 BV');

      expect(result).toMatchObject({
        normalized_reference: null,
        resolved: false,
        unresolved_reason: 'not_normalizable',
        targets: [],
      });
      // It must not have even tried to search — a guess here is worse than a miss.
      expect(repository.findTargetsByKey).not.toHaveBeenCalled();
    });

    it('distinguishes a coverage gap from an extractor gap', async () => {
      // Valid key, but the norm simply is not in the corpus. That is a DIFFERENT
      // problem from a citation we could not parse, and conflating the two hides
      // which one to go fix.
      (repository.findTargetsByKey as ReturnType<typeof vi.fn>).mockResolvedValue([]);

      const result = await service.resolve('SR 210');

      expect(result).toMatchObject({
        normalized_reference: 'sr:210',
        resolved: false,
        unresolved_reason: 'no_target_in_corpus',
      });
    });
  });

  describe('find_citing', () => {
    it('returns the citing document when asked by canonical key', async () => {
      (repository.findTargetsByKey as ReturnType<typeof vi.fn>).mockResolvedValue([ZGB]);
      (repository.findCitingEdges as ReturnType<typeof vi.fn>).mockResolvedValue([BV_CITES_ZGB]);

      const result = await service.findCiting('sr:210');

      expect(result.normalized_references).toEqual(['sr:210']);
      expect(result.total).toBe(1);
      expect(result.citing[0].source_document_id).toBe('doc_bv');
    });

    it('returns the citing document when asked by document id', async () => {
      (repository.findTargetsByDocumentId as ReturnType<typeof vi.fn>).mockResolvedValue([ZGB]);
      (repository.findCitingEdges as ReturnType<typeof vi.fn>).mockResolvedValue([BV_CITES_ZGB]);

      const result = await service.findCiting('doc_zgb');

      expect(repository.findTargetsByDocumentId).toHaveBeenCalledWith('doc_zgb');
      // The document id was translated into the key it IS, and traversal ran on
      // the key — which is why it works even though BV_CITES_ZGB carries no
      // target_document_id.
      expect(repository.findCitingEdges).toHaveBeenCalledWith({
        normalizedReferences: ['sr:210'],
        documentId: 'doc_zgb',
        limit: 50,
      });
      expect(result.citing[0].source_document_id).toBe('doc_bv');
    });

    it('traverses through the key, so edge direction survives projection order', async () => {
      // BV_CITES_ZGB has target_document_id: undefined — the ZGB was projected
      // after the BV. A reverse lookup keyed on target_document_id (which is what
      // /cited_by does) would return nothing here. Keying on `sr:210` finds it.
      (repository.findTargetsByDocumentId as ReturnType<typeof vi.fn>).mockResolvedValue([ZGB]);
      (repository.findCitingEdges as ReturnType<typeof vi.fn>).mockResolvedValue([BV_CITES_ZGB]);

      const result = await service.findCiting('doc_zgb');

      expect(BV_CITES_ZGB.target_document_id).toBeUndefined();
      expect(result.total).toBe(1);
    });

    it('excludes the norm citing itself from its own masthead', async () => {
      // A statute's masthead states its own SR number, which extraction picks up
      // as a citation. "The BV cites the BV" is not an answer to "what cites the BV".
      const selfCitation: CitationEdge = {
        citation_id: 'cit_self',
        source_document_id: 'doc_bv',
        citation_text: 'SR 101',
        citation_type: 'sr',
        normalized_reference: 'sr:101',
      };
      (repository.findTargetsByDocumentId as ReturnType<typeof vi.fn>).mockResolvedValue([BV]);
      (repository.findCitingEdges as ReturnType<typeof vi.fn>).mockResolvedValue([
        selfCitation,
        { ...BV_CITES_ZGB, citation_id: 'cit_2', source_document_id: 'doc_other' },
      ]);

      const result = await service.findCiting('doc_bv');

      expect(result.total).toBe(1);
      expect(result.citing[0].source_document_id).toBe('doc_other');
    });

    it('returns nothing for a fuzzy query rather than a similarity fallback', async () => {
      const result = await service.findCiting('Art. 36 BV');

      expect(result).toMatchObject({ normalized_references: [], citing: [], total: 0 });
      expect(repository.findCitingEdges).not.toHaveBeenCalled();
    });
  });

  describe('resolution rate', () => {
    it('reports the rate and attributes every unresolved citation', async () => {
      (repository.getResolutionStats as ReturnType<typeof vi.fn>).mockResolvedValue({
        total: 504,
        withNormalizedReference: 120,
        resolvable: 42,
        unresolvedByType: { article: 300, bge: 84, unresolved_target: 78 },
      });

      const stats = await service.getStats();

      expect(stats.citations_total).toBe(504);
      expect(stats.citations_resolved).toBe(42);
      expect(stats.resolution_rate).toBeCloseTo(0.0833, 4);
      // The unresolved remainder is not a rounding error to be hidden — it is
      // the work queue.
      expect(stats.unresolved_by_type).toEqual({
        article: 300,
        bge: 84,
        unresolved_target: 78,
      });
    });

    it('reports a zero rate for an empty graph instead of dividing by zero', async () => {
      const stats = await service.getStats();
      expect(stats.resolution_rate).toBe(0);
      expect(stats.citations_total).toBe(0);
    });
  });
});
