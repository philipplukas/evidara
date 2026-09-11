import type { Response } from 'express';
import { describe, expect, it, vi } from 'vitest';
import type { ReadAliasCheck, SearchRepository } from '../search/search.repository';
import { HealthController } from './health.controller';

const ALIAS_OK: ReadAliasCheck = {
  status: 'ok',
  alias: 'documents-read',
  indices: ['documents-000001'],
};

const ALIAS_MISSING: ReadAliasCheck = {
  status: 'error',
  alias: 'documents-read',
  detail: 'index_not_found_exception: no such index [documents-read]',
};

function createController(options?: {
  ping?: () => Promise<unknown>;
  readAlias?: ReadAliasCheck;
}): HealthController {
  const repository = {
    search: vi.fn(),
    getContextAggregations: vi.fn(),
    getHeldJurisdictionIds: vi.fn(),
    checkReadAlias: vi.fn().mockResolvedValue(options?.readAlias ?? ALIAS_OK),
  } satisfies SearchRepository;

  return new HealthController(
    { ping: options?.ping ?? (async () => ({})) } as never,
    repository as SearchRepository,
  );
}

/** Minimal `@Res({ passthrough: true })` stand-in that records the status. */
function createResponse() {
  const status = vi.fn();
  return { res: { status } as unknown as Response, status };
}

describe('HealthController', () => {
  it('should return ok status', () => {
    const result = createController().check();
    expect(result.status).toBe('ok');
    expect(result.timestamp).toBeDefined();
  });

  it('should report ready when opensearch pings and the read alias resolves', async () => {
    const { res, status } = createResponse();

    const result = await createController().ready(res);

    expect(result.status).toBe('ok');
    expect(result.checks.opensearch.status).toBe('ok');
    expect(result.checks.documents_read_alias).toEqual(ALIAS_OK);
    expect(status).not.toHaveBeenCalled();
  });

  it('should report degraded with 503 when opensearch ping fails', async () => {
    const { res, status } = createResponse();
    const controller = createController({
      ping: async () => {
        throw new Error('connection failed');
      },
    });

    const result = await controller.ready(res);

    expect(result.status).toBe('degraded');
    expect(result.checks.opensearch.status).toBe('error');
    expect(status).toHaveBeenCalledWith(503);
  });

  it('should report degraded with 503 when the documents read alias does not resolve', async () => {
    const { res, status } = createResponse();
    const controller = createController({ readAlias: ALIAS_MISSING });

    const result = await controller.ready(res);

    // The cluster is up — but a pod that cannot see `documents-read` cannot
    // serve search and must not claim to be ready (#551).
    expect(result.checks.opensearch.status).toBe('ok');
    expect(result.status).toBe('degraded');
    expect(result.checks.documents_read_alias).toEqual(ALIAS_MISSING);
    expect(status).toHaveBeenCalledWith(503);
  });
});
