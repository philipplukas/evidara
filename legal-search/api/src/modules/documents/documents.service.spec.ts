import { NotFoundException } from '@nestjs/common';
import { describe, expect, it, vi } from 'vitest';
import type { DocumentsRepository } from './documents.repository';
import { DocumentsService } from './documents.service';

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
    ...overrides,
  };
}

// ─── Tests ───

describe('DocumentsService', () => {
  it('should return a composed DetailView', async () => {
    const repo = createMockRepo();
    const service = new DocumentsService(repo);

    const detail = await service.getDetail('doc_001');

    expect(detail.id).toBe('doc_001');
    expect(detail.type).toBe('law');
    expect(detail.subtitle).toContain('Switzerland');
    expect(detail.tabs.length).toBeGreaterThan(0);
    expect(detail.references).toHaveLength(1);
    expect(detail.localStructure?.items).toHaveLength(1);
  });

  it('should throw NotFoundException for missing document', async () => {
    const repo = createMockRepo({
      getById: vi.fn().mockResolvedValue(null),
    });
    const service = new DocumentsService(repo);

    await expect(service.getDetail('doc_missing')).rejects.toThrow(NotFoundException);
  });

  it('should always return arrays per ADR-0011', async () => {
    const repo = createMockRepo({
      getSections: vi.fn().mockResolvedValue([]),
      getCitations: vi.fn().mockResolvedValue([]),
    });
    const service = new DocumentsService(repo);

    const detail = await service.getDetail('doc_001');

    expect(Array.isArray(detail.metadata)).toBe(true);
    expect(Array.isArray(detail.tabs)).toBe(true);
    expect(Array.isArray(detail.relatedGroups)).toBe(true);
    expect(Array.isArray(detail.references)).toBe(true);
    expect(Array.isArray(detail.annotations)).toBe(true);
  });

  it('should delegate getSections to repository', async () => {
    const repo = createMockRepo();
    const service = new DocumentsService(repo);

    const sections = await service.getSections('doc_001');

    expect(repo.getSections).toHaveBeenCalledWith('doc_001');
    expect(sections).toHaveLength(1);
  });
});
