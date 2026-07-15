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
})
export class CitationsModule {}
