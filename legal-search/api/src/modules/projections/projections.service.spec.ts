import { describe, expect, it, vi } from 'vitest';
import type { DocumentIntelligenceClient } from '../../lib/document-intelligence/document-intelligence.client';
import type {
  DocumentProcessedEventDto,
  DocumentWithdrawnEventDto,
} from './dto/projection-events.dto';
import type { ProjectionRepository } from './projections.repository';
import { ProjectionsService } from './projections.service';

function createRepositoryMock(): ProjectionRepository {
  return {
    hasHistoryEvent: vi.fn().mockResolvedValue(false),
    getLatestRevision: vi.fn().mockResolvedValue(null),
    upsertProjection: vi.fn().mockResolvedValue(undefined),
    deleteProjection: vi.fn().mockResolvedValue(undefined),
    appendHistory: vi.fn().mockResolvedValue(undefined),
    queryHistory: vi.fn().mockResolvedValue({ data: [], total: 0, limit: 50, offset: 0 }),
    getHistoryStats: vi.fn().mockResolvedValue({
      totalEvents: 0,
      applied: 0,
      stale: 0,
      ignoredDuplicate: 0,
      uniqueDocuments: 0,
    }),
  };
}

function createDocumentIntelligenceMock(): DocumentIntelligenceClient {
  return {
    fetchLeanDocument: vi.fn().mockResolvedValue({}),
  };
}

const baseProcessedEvent: DocumentProcessedEventDto = {
  event_id: 'evt_1',
  event_type: 'document.processed',
  event_version: 1,
  occurred_at: '2026-04-03T10:00:00Z',
  producer: 'document-intelligence',
  payload: {
    document_id: 'doc_01jq7bhgy7g0pkj4f1d03f8f8c',
    document_revision: 2,
    processing_manifest_id: 'pm_01jq7bhgy7g0pkj4f1d03f8f8c',
    processing_version: 'v1.0.0',
    authority_id: 'auth_fedlex',
    authority_name: 'Fedlex',
    is_official: true,
    lifecycle_status: 'active',
    provenance: {
      tenant_id: 'tenant_evidara',
      corpus_id: 'ch_de',
      scope_type: 'source-version',
      source_id: 'src_01jq7bhgy7g0pkj4f1d03f8f8c',
      source_version_id: 'sv_01jq7bhgy7g0pkj4f1d03f8f8c',
      run_id: 'run_01jq7bhgy7g0pkj4f1d03f8f8c',
    },
  },
};

const baseWithdrawnEvent: DocumentWithdrawnEventDto = {
  event_id: 'evt_2',
  event_type: 'document.withdrawn',
  event_version: 1,
  occurred_at: '2026-04-03T10:05:00Z',
  producer: 'document-intelligence',
  payload: {
    document_id: 'doc_01jq7bhgy7g0pkj4f1d03f8f8c',
    document_revision: 3,
    processing_manifest_id: 'pm_01jq7chgy7g0pkj4f1d03f8f8c',
    provenance: {
      tenant_id: 'tenant_evidara',
      corpus_id: 'ch_de',
      scope_type: 'source-version',
      source_id: 'src_01jq7bhgy7g0pkj4f1d03f8f8c',
      source_version_id: 'sv_01jq7bhgy7g0pkj4f1d03f8f8c',
      run_id: 'run_01jq7bhgy7g0pkj4f1d03f8f8c',
    },
    reason_code: 'operator_withdrawn',
    reason_summary: 'manual',
    search_disposition: 'remove',
  },
};

describe('ProjectionsService', () => {
  it('applies a fresh processed event and writes history', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    const service = new ProjectionsService(repository, diClient);

    const result = await service.applyDocumentProcessed(baseProcessedEvent);

    expect(result.status).toBe('applied');
    expect(repository.upsertProjection).toHaveBeenCalledTimes(1);
    expect(repository.appendHistory).toHaveBeenCalledTimes(1);
  });

  it('ignores duplicate events by event_id', async () => {
    const repository = createRepositoryMock();
    (repository.hasHistoryEvent as ReturnType<typeof vi.fn>).mockResolvedValue(true);
    const diClient = createDocumentIntelligenceMock();
    const service = new ProjectionsService(repository, diClient);

    const result = await service.applyDocumentProcessed(baseProcessedEvent);

    expect(result.status).toBe('ignored_duplicate');
    expect(repository.upsertProjection).not.toHaveBeenCalled();
    expect(repository.appendHistory).not.toHaveBeenCalled();
  });

  it('marks stale processed events when revision regresses', async () => {
    const repository = createRepositoryMock();
    (repository.getLatestRevision as ReturnType<typeof vi.fn>).mockResolvedValue(5);
    const diClient = createDocumentIntelligenceMock();
    const service = new ProjectionsService(repository, diClient);

    const event = {
      ...baseProcessedEvent,
      payload: { ...baseProcessedEvent.payload, document_revision: 4 },
    };
    const result = await service.applyDocumentProcessed(event);

    expect(result.status).toBe('stale');
    expect(repository.upsertProjection).not.toHaveBeenCalled();
    expect(repository.appendHistory).toHaveBeenCalledWith(
      expect.objectContaining({ status: 'stale' }),
    );
  });

  it('removes projection for withdrawn event and writes history', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    const service = new ProjectionsService(repository, diClient);

    const result = await service.applyDocumentWithdrawn(baseWithdrawnEvent);

    expect(result.status).toBe('applied');
    expect(repository.deleteProjection).toHaveBeenCalledWith(
      baseWithdrawnEvent.payload.document_id,
    );
    expect(repository.appendHistory).toHaveBeenCalledTimes(1);
  });

  it('uses lean document fields when available', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'Bundesgerichtsurteil 9C_100/2025',
      language: 'de',
      metadata: {
        official_citation: 'SR 101',
        original_language: 'de',
        translation_status: 'original',
      },
      sections: [{ id: 's1' }, { id: 's2' }],
      citations: [{ id: 'c1' }],
      content_text: 'Leitsatz und Sachverhalt...',
    });
    const service = new ProjectionsService(repository, diClient);

    await service.applyDocumentProcessed(baseProcessedEvent);

    expect(repository.upsertProjection).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Bundesgerichtsurteil 9C_100/2025',
        authority_name: 'Fedlex',
        official_citation: 'SR 101',
        original_language: 'de',
        translation_status: 'original',
        is_official: true,
        sections_count: 2,
        citations_count: 1,
        language: 'de',
        lifecycle_status: 'active',
        content_preview: 'Leitsatz und Sachverhalt...',
      }),
    );
  });

  it('maps canonical published-document lean rows into projection metadata', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'BVGE 123/2024',
      document_type: 'decision',
      effective_date: '2024-06-01',
      jurisdiction_id: 'ch_zh',
      language: 'de',
      body_text: 'Kurzfassung des Urteils mit ausreichend Text für eine Vorschau.',
      metadata: {
        extracted_metadata: {
          structural_path: 'BGer › Zivilrecht',
        },
      },
      extensions: {
        citations: [{ id: 'c1' }],
      },
    });
    const service = new ProjectionsService(repository, diClient);

    await service.applyDocumentProcessed(baseProcessedEvent);

    expect(repository.upsertProjection).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'BVGE 123/2024',
        document_type: 'decision',
        effective_date: '2024-06-01',
        jurisdiction: 'CH',
        structural_path: 'BGer › Zivilrecht',
        citations_count: 1,
        content_preview: expect.stringContaining('Kurzfassung'),
      }),
    );
  });

  it('normalizes aliased document type hints from lean metadata before indexing', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    const service = new ProjectionsService(repository, diClient);

    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      metadata: {
        source_defaults: {
          document_type_hint: 'statute',
        },
      },
    });
    await service.applyDocumentProcessed({
      ...baseProcessedEvent,
      event_id: 'evt_5',
      payload: { ...baseProcessedEvent.payload, document_id: 'doc_4' },
    });
    expect(repository.upsertProjection).toHaveBeenLastCalledWith(
      expect.objectContaining({
        document_type: 'law',
      }),
    );

    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      metadata: {
        source_defaults: {
          document_type_hint: 'legislation',
        },
      },
    });
    await service.applyDocumentProcessed({
      ...baseProcessedEvent,
      event_id: 'evt_5b',
      payload: { ...baseProcessedEvent.payload, document_id: 'doc_4b' },
    });
    expect(repository.upsertProjection).toHaveBeenLastCalledWith(
      expect.objectContaining({
        document_type: 'law',
      }),
    );

    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      metadata: {
        extracted_metadata: {
          document_type: 'urteil',
        },
      },
    });
    await service.applyDocumentProcessed({
      ...baseProcessedEvent,
      event_id: 'evt_6',
      payload: { ...baseProcessedEvent.payload, document_id: 'doc_5' },
    });
    expect(repository.upsertProjection).toHaveBeenLastCalledWith(
      expect.objectContaining({
        document_type: 'decision',
      }),
    );
  });

  it('falls back to LLM title when canonical title is a placeholder', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'Untitled document',
      metadata: {
        llm_extraction: {
          applied: true,
          title: 'Bundesgericht 2C_123/2024',
          structural_path: 'BGer › Öffentliches Recht',
        },
      },
    });
    const service = new ProjectionsService(repository, diClient);

    await service.applyDocumentProcessed(baseProcessedEvent);

    expect(repository.upsertProjection).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Bundesgericht 2C_123/2024',
      }),
    );
  });

  it('extracts embedded Fedlex titles from JSON-shaped lean bodies when the canonical title is a placeholder', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'Untitled document',
      body_text: JSON.stringify({
        title: 'Bundesverfassung der Schweizerischen Eidgenossenschaft vom 18. April 1999',
        body: 'Bundesverfassung ...',
      }),
    });
    const service = new ProjectionsService(repository, diClient);

    await service.applyDocumentProcessed(baseProcessedEvent);

    expect(repository.upsertProjection).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Bundesverfassung der Schweizerischen Eidgenossenschaft vom 18. April 1999',
      }),
    );
  });

  it('extracts embedded titles from array-shaped JSON lean bodies when the canonical title is a placeholder', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'Untitled document',
      body_text: JSON.stringify([
        {
          section: {
            title: 'Bundesgesetz über das Bundesgericht',
            body: 'BGG ...',
          },
        },
      ]),
    });
    const service = new ProjectionsService(repository, diClient);

    await service.applyDocumentProcessed(baseProcessedEvent);

    expect(repository.upsertProjection).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Bundesgesetz über das Bundesgericht',
      }),
    );
  });

  it('treats RIS placeholder titles as missing and falls back to embedded JSON titles', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'RIS Dokument',
      body_text: JSON.stringify({
        title: 'Bundesgesetz über das Bundesgericht',
        body: 'BGG ...',
      }),
    });
    const service = new ProjectionsService(repository, diClient);

    await service.applyDocumentProcessed(baseProcessedEvent);

    expect(repository.upsertProjection).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Bundesgesetz über das Bundesgericht',
      }),
    );
  });

  it('falls back to citation, substantive text, and structural-path tail for missing titles', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    const service = new ProjectionsService(repository, diClient);

    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'Untitled document',
      metadata: {
        official_citation: 'BGE 150 II 10',
      },
      body_text: 'Kurz.\nDies ist eine ausreichend lange Titel-ähnliche Zeile.',
      structural_path: 'BGer › Zivilrecht',
    });
    await service.applyDocumentProcessed(baseProcessedEvent);
    expect(repository.upsertProjection).toHaveBeenLastCalledWith(
      expect.objectContaining({ title: 'BGE 150 II 10' }),
    );

    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'Untitled document',
      body_text: 'Kurz.\nDies ist eine ausreichend lange Titel-ähnliche Zeile.',
      structural_path: 'BGer › Zivilrecht',
    });
    await service.applyDocumentProcessed({
      ...baseProcessedEvent,
      event_id: 'evt_3',
      payload: { ...baseProcessedEvent.payload, document_id: 'doc_2' },
    });
    expect(repository.upsertProjection).toHaveBeenLastCalledWith(
      expect.objectContaining({
        title: 'Dies ist eine ausreichend lange Titel-ähnliche Zeile.',
      }),
    );

    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'Untitled document',
      structural_path: 'BGer › Zivilrecht',
    });
    await service.applyDocumentProcessed({
      ...baseProcessedEvent,
      event_id: 'evt_4',
      payload: { ...baseProcessedEvent.payload, document_id: 'doc_3' },
    });
    expect(repository.upsertProjection).toHaveBeenLastCalledWith(
      expect.objectContaining({ title: 'Zivilrecht' }),
    );
  });

  it('extracts structured Fedlex titles from JSON body payloads before using raw text fallback', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    const service = new ProjectionsService(repository, diClient);

    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue({
      title: 'Untitled document',
      body_text: JSON.stringify({
        final_url: 'https://fedlex.data.admin.ch/eli/cc/1999/404',
        inline_body: JSON.stringify({
          provider: 'fedlex_sparql',
          title: 'Bundesverfassung der Schweizerischen Eidgenossenschaft vom 18. April 1999',
          title_short: 'BV',
        }),
      }),
      metadata: {
        source_defaults: {
          authority_id: 'auth_fedlex',
          document_type_hint: 'legislation',
        },
      },
    });

    await service.applyDocumentProcessed({
      ...baseProcessedEvent,
      event_id: 'evt_4b',
      payload: { ...baseProcessedEvent.payload, document_id: 'doc_fedlex' },
    });

    expect(repository.upsertProjection).toHaveBeenLastCalledWith(
      expect.objectContaining({
        title: 'Bundesverfassung der Schweizerischen Eidgenossenschaft vom 18. April 1999',
        document_type: 'law',
      }),
    );
  });

  it('applies projection with fallback fields when DI enrichment is unavailable', async () => {
    const repository = createRepositoryMock();
    const diClient = createDocumentIntelligenceMock();
    (diClient.fetchLeanDocument as ReturnType<typeof vi.fn>).mockResolvedValue(null);
    const service = new ProjectionsService(repository, diClient);

    const result = await service.applyDocumentProcessed(baseProcessedEvent);

    expect(result.status).toBe('applied');
    expect(repository.upsertProjection).toHaveBeenCalledWith(
      expect.objectContaining({
        title: `Document ${baseProcessedEvent.payload.document_id}`,
        authority_name: 'Fedlex',
        is_official: true,
        sections_count: 0,
        citations_count: 0,
        lifecycle_status: 'active',
      }),
    );
    expect(repository.appendHistory).toHaveBeenCalledTimes(1);
  });
});
