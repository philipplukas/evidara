import { Module } from '@nestjs/common';
import { SearchOpenSearchAdapter } from './opensearch.adapter';
import { SearchController } from './search.controller';
import { SEARCH_REPOSITORY } from './search.repository';
import { SearchService } from './search.service';

@Module({
  controllers: [SearchController],
  providers: [SearchService, { provide: SEARCH_REPOSITORY, useClass: SearchOpenSearchAdapter }],
  // HealthModule consumes the repository for the read-alias readiness check —
  // OpenSearch calls stay inside the adapter (ADR-0008).
  exports: [SEARCH_REPOSITORY],
})
export class SearchModule {}
