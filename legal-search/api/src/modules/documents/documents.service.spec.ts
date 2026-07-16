import { NotFoundException } from '@nestjs/common';
import { describe, expect, it, vi } from 'vitest';
import type { DocumentIntelligenceClient } from '../../lib/document-intelligence/document-intelligence.client';
import type { DocumentsRepository } from './documents.repository';
import { DocumentsService } from './documents.service';

function createNoopDiClient(): DocumentIntelligenceClient {
  return { fetchLeanDocument: vi.fn().mockResolvedValue(null) };
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
    const service = new DocumentsService(repo, createNoopDiClient());

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
    const service = new DocumentsService(repo, createNoopDiClient());

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
    const service = new DocumentsService(repo, { fetchLeanDocument });

    const detail = await service.getDetail('doc_001', undefined, 'corr-1');

    expect(fetchLeanDocument).toHaveBeenCalledWith('doc_001', { correlationId: 'corr-1' });
    expect(detail.content).toBe('Erste Erwägung.\n\nZweite Erwägung.');
  });

  it('should leave content absent when the Document Service has no body either', async () => {
    const fetchLeanDocument = vi.fn().mockResolvedValue({ document_id: 'doc_001' });
    const service = new DocumentsService(createMockRepo(), { fetchLeanDocument });

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
    const service = new DocumentsService(repo, { fetchLeanDocument });

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
    const service = new DocumentsService(repo, createNoopDiClient());

    const detail = await service.getDetail('doc_001');

    expect(Array.isArray(detail.metadata)).toBe(true);
    expect(Array.isArray(detail.tabs)).toBe(true);
    expect(Array.isArray(detail.relatedGroups)).toBe(true);
    expect(Array.isArray(detail.references)).toBe(true);
    expect(Array.isArray(detail.annotations)).toBe(true);
  });

  it('should delegate getSections to repository', async () => {
    const repo = createMockRepo();
    const service = new DocumentsService(repo, createNoopDiClient());

    const sections = await service.getSections('doc_001');

    expect(repo.getSections).toHaveBeenCalledWith('doc_001');
    expect(sections).toHaveLength(1);
  });
});
