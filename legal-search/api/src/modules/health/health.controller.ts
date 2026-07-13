import { Controller, Get, HttpStatus, Inject, Res } from '@nestjs/common';
import type { Client } from '@opensearch-project/opensearch';
import type { Response } from 'express';
import { Public } from '../../core/auth/public.decorator';
import { OPENSEARCH_CLIENT } from '../../core/opensearch/client';
import { SEARCH_REPOSITORY, type SearchRepository } from '../search/search.repository';

type DependencyCheck = { status: 'ok' } | { status: 'error'; detail: string };

@Public()
@Controller('health')
export class HealthController {
  constructor(
    @Inject(OPENSEARCH_CLIENT) private readonly opensearch: Client,
    @Inject(SEARCH_REPOSITORY) private readonly searchRepository: SearchRepository,
  ) {}

  @Get()
  check() {
    return { status: 'ok', timestamp: new Date().toISOString() };
  }

  /**
   * Readiness: a pod that cannot reach OpenSearch, or cannot see the
   * documents read alias, cannot serve search and must not claim to be
   * ready (#551). Reports 503 so the failure is visible to probes,
   * uptime checks, and `curl /health/ready` in the release runbook —
   * instead of a silently empty search index.
   */
  @Get('ready')
  async ready(@Res({ passthrough: true }) res?: Response) {
    const [opensearch, documentsReadAlias] = await Promise.all([
      this.pingCluster(),
      this.searchRepository.checkReadAlias(),
    ]);

    const ready = opensearch.status === 'ok' && documentsReadAlias.status === 'ok';
    if (!ready) res?.status(HttpStatus.SERVICE_UNAVAILABLE);

    return {
      status: ready ? ('ok' as const) : ('degraded' as const),
      checks: {
        opensearch,
        documents_read_alias: documentsReadAlias,
      },
    };
  }

  private async pingCluster(): Promise<DependencyCheck> {
    try {
      await this.opensearch.ping();
      return { status: 'ok' };
    } catch (error) {
      return {
        status: 'error',
        detail: error instanceof Error ? error.message : String(error),
      };
    }
  }
}
