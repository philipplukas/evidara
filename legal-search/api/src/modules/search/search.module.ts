import { Module } from '@nestjs/common';
import { SearchController } from './search.controller';
import { SearchService } from './search.service';
import { OpenSearchSearchAdapter } from './opensearch.adapter';
import { SEARCH_REPOSITORY } from './search.repository';

@Module({
  controllers: [SearchController],
  providers: [
    SearchService,
    // Bind the interface token to the concrete adapter.
    // To test SearchService in isolation, provide a mock for SEARCH_REPOSITORY.
    {
      provide: SEARCH_REPOSITORY,
      useClass: OpenSearchSearchAdapter,
    },
  ],
})
export class SearchModule {}
