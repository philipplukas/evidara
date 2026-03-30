import { Module } from '@nestjs/common';
import { SearchOpenSearchAdapter } from './opensearch.adapter';
import { SearchController } from './search.controller';
import { SEARCH_REPOSITORY } from './search.repository';
import { SearchService } from './search.service';

@Module({
  controllers: [SearchController],
  providers: [SearchService, { provide: SEARCH_REPOSITORY, useClass: SearchOpenSearchAdapter }],
})
export class SearchModule {}
