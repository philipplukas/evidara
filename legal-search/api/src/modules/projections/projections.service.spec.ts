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
      sections: [{ id: 's1' }, { id: 's2' }],
      citations: [{ id: 'c1' }],
      content_text: 'Leitsatz und Sachverhalt...',
    });
    const service = new ProjectionsService(repository, diClient);

    await service.applyDocumentProcessed(baseProcessedEvent);

    expect(repository.upsertProjection).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Bundesgerichtsurteil 9C_100/2025',
        sections_count: 2,
        citations_count: 1,
        language: 'de',
        lifecycle_status: 'active',
        content_preview: 'Leitsatz und Sachverhalt...',
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
        sections_count: 0,
        citations_count: 0,
        lifecycle_status: 'active',
      }),
    );
    expect(repository.appendHistory).toHaveBeenCalledTimes(1);
  });
});
