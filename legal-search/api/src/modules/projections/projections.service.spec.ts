import { describe, expect, it, vi } from 'vitest';
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
    const service = new ProjectionsService(repository);

    const result = await service.applyDocumentProcessed(baseProcessedEvent);

    expect(result.status).toBe('applied');
    expect(repository.upsertProjection).toHaveBeenCalledTimes(1);
    expect(repository.appendHistory).toHaveBeenCalledTimes(1);
  });

  it('ignores duplicate events by event_id', async () => {
    const repository = createRepositoryMock();
    (repository.hasHistoryEvent as ReturnType<typeof vi.fn>).mockResolvedValue(true);
    const service = new ProjectionsService(repository);

    const result = await service.applyDocumentProcessed(baseProcessedEvent);

    expect(result.status).toBe('ignored_duplicate');
    expect(repository.upsertProjection).not.toHaveBeenCalled();
    expect(repository.appendHistory).not.toHaveBeenCalled();
  });

  it('marks stale processed events when revision regresses', async () => {
    const repository = createRepositoryMock();
    (repository.getLatestRevision as ReturnType<typeof vi.fn>).mockResolvedValue(5);
    const service = new ProjectionsService(repository);

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
    const service = new ProjectionsService(repository);

    const result = await service.applyDocumentWithdrawn(baseWithdrawnEvent);

    expect(result.status).toBe('applied');
    expect(repository.deleteProjection).toHaveBeenCalledWith(
      baseWithdrawnEvent.payload.document_id,
    );
    expect(repository.appendHistory).toHaveBeenCalledTimes(1);
  });
});
