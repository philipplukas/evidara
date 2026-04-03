import { Controller, Get, Inject } from '@nestjs/common';
import type { Client } from '@opensearch-project/opensearch';
import { OPENSEARCH_CLIENT } from '../../core/opensearch/client';

@Controller('health')
export class HealthController {
  constructor(@Inject(OPENSEARCH_CLIENT) private readonly opensearch: Client) {}

  @Get()
  check() {
    return { status: 'ok', timestamp: new Date().toISOString() };
  }

  @Get('ready')
  async ready() {
    try {
      await this.opensearch.ping();
      return {
        status: 'ok',
        checks: { opensearch: { status: 'ok' } },
      };
    } catch (error) {
      return {
        status: 'degraded',
        checks: {
          opensearch: {
            status: 'error',
            detail: error instanceof Error ? error.message : String(error),
          },
        },
      };
    }
  }
}
