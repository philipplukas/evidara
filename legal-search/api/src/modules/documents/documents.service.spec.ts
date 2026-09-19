import { NotFoundException, ServiceUnavailableException } from '@nestjs/common';
import { describe, expect, it, vi } from 'vitest';
import {
  type DocumentIntelligenceClient,
  LeanDocumentUnavailableError,
} from '../../lib/document-intelligence/document-intelligence.client';
import type { CitationsRepository } from '../citations/citations.repository';
import type { DocumentsRepository } from './documents.repository';
import { DocumentsService } from './documents.service';

function createNoopDiClient(): DocumentIntelligenceClient {
  return { fetchLeanDocument: vi.fn().mockResolvedValue(null) };
}

function createMockCitationsRepo(overrides?: Partial<CitationsRepository>): CitationsRepository {
  return {
    findTargetsByKey: vi.fn().mockResolvedValue([]),
    findTargetsByKeys: vi.fn().mockResolvedValue(new Map()),
    findTargetsByDocumentId: vi.fn().mockResolvedValue([]),
    findCitingEdges: vi.fn().mockResolvedValue([]),
    getResolutionStats: vi.fn().mockResolvedValue({
      total: 0,
      withNormalizedReference: 0,
      resolvable: 0,
      unresolvedByType: {},
    }),
    ...overrides,
  };
}

// ─── Mock Repository ───

function createMockRepo(overrides?: Partial<DocumentsRepository>): DocumentsRepository {
  return {
    getById: vi.fn().mockResolvedValue({
      document_id: 'doc_001',
      title: 'Test Law',
      document_type: 'law',
      jurisdiction: 'CH',
      effective_date: '2024-01-01',
      sections_count: 2,
      citations_count: 1,
    }),
    getSections: vi.fn().mockResolvedValue([
      {
        section_id: 'sec_001',
        document_id: 'doc_001',
        title: 'Section 1',
        ordinal: 0,
        depth: 0,
      },
    ]),
    getCitations: vi.fn().mockResolvedValue([
      {
        citation_id: 'cit_001',
        source_document_id: 'doc_001',
        citation_text: 'Art. 1 OR',
        citation_type: 'statute_reference',
        resolved: true,
      },
    ]),
    getCitedBy: vi.fn().mockResolvedValue([]),
    ...overrides,
  };
}

// ─── Tests ───

describe('DocumentsService', () => {
  it('should return a composed DetailView', async () => {
    const repo = createMockRepo();
    const service = new DocumentsService(repo, createNoopDiClient(), createMockCitationsRepo());

    const detail = await service.getDetail('doc_001');

    expect(detail.id).toBe('doc_001');
    expect(detail.type).toBe('law');
    expect(detail.subtitle).toContain('Schweiz');
    expect(detail.tabs.length).toBeGreaterThan(0);
    expect(detail.references).toHaveLength(1);
    expect(detail.localStructure?.items).toHaveLength(1);
  });

  it('should throw NotFoundException for missing document', async () => {
    const repo = createMockRepo({
      getById: vi.fn().mockResolvedValue(null),
    });
    const service = new DocumentsService(repo, createNoopDiClient(), createMockCitationsRepo());

    await expect(service.getDetail('doc_missing')).rejects.toThrow(NotFoundException);
  });

  // The Document Service's `/lean` reply is a canonical row carrying
  // `body_text`, NOT the DoclingDocument its spec advertises: `service/lean.py`
  // validates the payload as a DoclingDocument, always fails, and returns the
  // stripped canonical dict instead. This fixture is that real shape — the
  // previous one (`{ schema_name: 'docling', version: '1' }`) was a payload the
  // service cannot emit.
  it('should take the body text from the Document Service when the index has none', async () => {
    const fetchLeanDocument = vi.fn().mockResolvedValue({
      document_id: 'doc_001',
      title: 'Test Law',
      body_text: 'Erste Erwägung.\n\nZweite Erwägung.',
      full_text: 'Test Law\n\nErste Erwägung.\n\nZweite Erwägung.',
    });
    const repo = createMockRepo();
    const service = new DocumentsService(repo, { fetchLeanDocument }, createMockCitationsRepo());

    const detail = await service.getDetail('doc_001', undefined, 'corr-1');

    expect(fetchLeanDocument).toHaveBeenCalledWith('doc_001', { correlationId: 'corr-1' });
    expect(detail.content).toBe('Erste Erwägung.\n\nZweite Erwägung.');
  });

  it('should leave content absent when the Document Service has no body either', async () => {
    const fetchLeanDocument = vi.fn().mockResolvedValue({ document_id: 'doc_001' });
    const service = new DocumentsService(
      createMockRepo(),
      { fetchLeanDocument },
      createMockCitationsRepo(),
    );

    const detail = await service.getDetail('doc_001');

    expect(detail.content).toBeUndefined();
    expect(detail.tabs.map((t) => t.key)).not.toContain('content');
  });

  it('should not call Document Service when the index already has the body', async () => {
    const fetchLeanDocument = vi.fn();
    const repo = createMockRepo({
      getById: vi.fn().mockResolvedValue({
        document_id: 'doc_001',
        title: 'Test Law',
        document_type: 'law',
        jurisdiction: 'CH',
        effective_date: '2024-01-01',
        sections_count: 2,
        citations_count: 1,
        content: 'Der Volltext des Dokuments.',
      }),
    });
    const service = new DocumentsService(repo, { fetchLeanDocument }, createMockCitationsRepo());

    const detail = await service.getDetail('doc_001');

    expect(fetchLeanDocument).not.toHaveBeenCalled();
    // The regression from #613: having a body used to be exactly what caused
    // the body to be dropped.
    expect(detail.content).toBe('Der Volltext des Dokuments.');
  });

  it('should always return arrays per ADR-0011', async () => {
    const repo = createMockRepo({
      getSections: vi.fn().mockResolvedValue([]),
      getCitations: vi.fn().mockResolvedValue([]),
    });
    const service = new DocumentsService(repo, createNoopDiClient(), createMockCitationsRepo());

    const detail = await service.getDetail('doc_001');

    expect(Array.isArray(detail.metadata)).toBe(true);
    expect(Array.isArray(detail.tabs)).toBe(true);
    expect(Array.isArray(detail.relatedGroups)).toBe(true);
    expect(Array.isArray(detail.references)).toBe(true);
    expect(Array.isArray(detail.annotations)).toBe(true);
  });

  it('should delegate getSections to repository', async () => {
    const repo = createMockRepo();
    const service = new DocumentsService(repo, createNoopDiClient(), createMockCitationsRepo());

    const sections = await service.getSections('doc_001');

    expect(repo.getSections).toHaveBeenCalledWith('doc_001');
    expect(sections).toHaveLength(1);
  });
});

describe('DocumentsService read-time citation join (order independence)', () => {
  const unlinkedCitation = {
    citation_id: 'cit_1',
    source_document_id: 'doc_001',
    citation_text: 'Art. 36 BV',
    citation_type: 'article',
    normalized_reference: 'abbrev_art:BV/36',
    // Deliberately absent: the BV had not been projected when this document
    // was, so the write-time denormalization never happened. Before the read
    // join, that rendered as an unlinked string forever.
    target_document_id: undefined,
    resolved: false,
  };

  const bvTarget = {
    document_id: 'doc_bv',
    identifier_type: 'abbrev_art',
    identifier_value: 'BV/36',
    title: 'Bundesverfassung',
    document_type: 'law',
    section_id: 'sec_36',
  };

  // POSITIVE. An implementation that joins nothing fails here.
  it('links a citation whose target was projected after it', async () => {
    const repo = createMockRepo({
      getCitations: vi.fn().mockResolvedValue([unlinkedCitation]),
    });
    const citations = createMockCitationsRepo({
      findTargetsByKeys: vi.fn().mockResolvedValue(new Map([['abbrev_art:BV/36', [bvTarget]]])),
    });

    const detail = await new DocumentsService(repo, createNoopDiClient(), citations).getDetail(
      'doc_001',
    );

    const items = detail.references.flatMap((group) => group.items);
    expect(items[0].href).toBe('/documents/doc_bv');
    expect(items[0].title).toBe('Bundesverfassung');
  });

  // THE REFUSAL, on the read side too — the same rule, not a second one.
  it('leaves an ambiguous citation unlinked rather than picking a norm', async () => {
    const repo = createMockRepo({
      getCitations: vi.fn().mockResolvedValue([unlinkedCitation]),
    });
    const citations = createMockCitationsRepo({
      findTargetsByKeys: vi
        .fn()
        .mockResolvedValue(
          new Map([
            [
              'abbrev_art:BV/36',
              [bvTarget, { ...bvTarget, document_id: 'doc_other', title: 'Other norm' }],
            ],
          ]),
        ),
    });

    const detail = await new DocumentsService(repo, createNoopDiClient(), citations).getDetail(
      'doc_001',
    );

    const items = detail.references.flatMap((group) => group.items);
    expect(items[0].href).toBeUndefined();
    expect(items[0].title).toBe('Art. 36 BV');
  });

  it('leaves citations as indexed when the targets lookup fails', async () => {
    const repo = createMockRepo({
      getCitations: vi.fn().mockResolvedValue([unlinkedCitation]),
    });
    const citations = createMockCitationsRepo({
      findTargetsByKeys: vi.fn().mockRejectedValue(new Error('opensearch unavailable')),
    });

    const detail = await new DocumentsService(repo, createNoopDiClient(), citations).getDetail(
      'doc_001',
    );

    expect(detail.references.flatMap((g) => g.items)[0].href).toBeUndefined();
  });

  describe('a failed body read is not an empty document (#984)', () => {
    // `getDetail` asks document-intelligence for a body only when the index has
    // none. Before #984 every reason for not getting one produced the same page:
    // a document rendered without content and without a content tab. That page
    // is a claim — "we hold no text for this norm" — and a 503 from the upstream
    // is not evidence for it.

    it('renders without a body when the upstream says there is none', async () => {
      const fetchLeanDocument = vi.fn().mockResolvedValue(null);
      const service = new DocumentsService(
        createMockRepo(),
        { fetchLeanDocument },
        createMockCitationsRepo(),
      );

      const detail = await service.getDetail('doc_001');

      expect(detail.content).toBeUndefined();
      expect(detail.tabs.map((t) => t.key)).not.toContain('content');
    });

    it('refuses with a 503 when the body read failed', async () => {
      const fetchLeanDocument = vi
        .fn()
        .mockRejectedValue(new LeanDocumentUnavailableError('doc_001', 503, 'upstream refused'));
      const service = new DocumentsService(
        createMockRepo(),
        { fetchLeanDocument },
        createMockCitationsRepo(),
      );

      const err = await service.getDetail('doc_001').then(
        () => {
          throw new Error('expected a refusal');
        },
        (e: unknown) => e,
      );

      expect(err).toBeInstanceOf(ServiceUnavailableException);
      expect((err as ServiceUnavailableException).getStatus()).toBe(503);
    });

    it('produces a different outcome for an absent body than for a failed read', async () => {
      // The assertion the issue asks for, stated as a comparison. It goes red
      // the moment the two collapse back into one value, whichever way round.
      const absent = new DocumentsService(
        createMockRepo(),
        { fetchLeanDocument: vi.fn().mockResolvedValue(null) },
        createMockCitationsRepo(),
      )
        .getDetail('doc_001')
        .then(
          () => 'rendered' as const,
          () => 'refused' as const,
        );

      const failed = new DocumentsService(
        createMockRepo(),
        {
          fetchLeanDocument: vi
            .fn()
            .mockRejectedValue(new LeanDocumentUnavailableError('doc_001', 500, 'boom')),
        },
        createMockCitationsRepo(),
      )
        .getDetail('doc_001')
        .then(
          () => 'rendered' as const,
          () => 'refused' as const,
        );

      expect(await absent).toBe('rendered');
      expect(await failed).toBe('refused');
      expect(await absent).not.toBe(await failed);
    });

    it('does not swallow an unrelated error as a body refusal', async () => {
      // A blanket catch here would re-flatten the distinction one level up:
      // everything would become "body unavailable", including bugs.
      const fetchLeanDocument = vi.fn().mockRejectedValue(new TypeError('programmer error'));
      const service = new DocumentsService(
        createMockRepo(),
        { fetchLeanDocument },
        createMockCitationsRepo(),
      );

      await expect(service.getDetail('doc_001')).rejects.toBeInstanceOf(TypeError);
    });
  });
});
