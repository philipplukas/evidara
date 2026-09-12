import { Module } from '@nestjs/common';
import { CitationsController } from './citations.controller';
import { CITATIONS_REPOSITORY } from './citations.repository';
import { CitationsService } from './citations.service';
import { CitationsOpenSearchAdapter } from './opensearch.adapter';

// `MetricsModule` is @Global, so `MetricsService` needs no explicit import.
@Module({
  controllers: [CitationsController],
  providers: [
    CitationsService,
    { provide: CITATIONS_REPOSITORY, useClass: CitationsOpenSearchAdapter },
  ],
  // The documents module resolves a document's citations at READ time through
  // this same port, so the target lookup has exactly one implementation.
  exports: [CITATIONS_REPOSITORY],
})
export class CitationsModule {}
