import { Controller, Get, Inject, Query } from '@nestjs/common';
import { SearchQueryDto } from './dto/search-query.dto';
import { SearchService } from './search.service';

@Controller('v1/search')
export class SearchController {
  constructor(
    @Inject(SearchService)
    private readonly searchService: SearchService,
  ) {}

  @Get()
  async search(@Query() query: SearchQueryDto) {
    return this.searchService.search(query.q, {
      jurisdiction: query.jurisdiction,
      documentType: query.document_type,
      page: query.page,
      pageSize: query.page_size,
    });
  }

  @Get('context')
  async getContext() {
    return this.searchService.getContext();
  }
}
