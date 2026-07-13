import { Global, Module } from '@nestjs/common';
import { MetricsController } from './metrics.controller';
import { MetricsService } from './metrics.service';
import { SearchIndexProbe } from './search-index.probe';

/**
 * Global so any adapter can inject `MetricsService` without importing a module —
 * the same pattern `OpenSearchModule` already uses for the OpenSearch client.
 */
@Global()
@Module({
  controllers: [MetricsController],
  providers: [MetricsService, SearchIndexProbe],
  exports: [MetricsService],
})
export class MetricsModule {}
