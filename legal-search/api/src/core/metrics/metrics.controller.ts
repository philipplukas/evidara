import { Controller, Get, Header, Inject } from '@nestjs/common';
import { Public } from '../auth/public.decorator';
import { MetricsService } from './metrics.service';
import { SearchIndexProbe } from './search-index.probe';

/**
 * Prometheus scrape endpoint. `@Public()` because the global `ApiKeyGuard` would
 * otherwise 401 the scraper — the port is cluster-internal (no Ingress route), same
 * exposure as `/health`.
 */
@Public()
@Controller('metrics')
export class MetricsController {
  // Explicit @Inject on every parameter, like the OpenSearch adapters: it makes DI
  // independent of emitted decorator metadata, and stops Biome's `useImportType` from
  // rewriting these to type-only imports (which would erase the tokens at runtime and
  // hand the constructor `undefined`).
  constructor(
    @Inject(MetricsService) private readonly metrics: MetricsService,
    @Inject(SearchIndexProbe) private readonly probe: SearchIndexProbe,
  ) {}

  @Get()
  @Header('Content-Type', 'text/plain; version=0.0.4; charset=utf-8')
  async scrape(): Promise<string> {
    await this.probe.refresh();
    return this.metrics.registry.metrics();
  }
}
