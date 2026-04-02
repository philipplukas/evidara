import { Controller, Get, Headers, Inject, Query } from '@nestjs/common';
import { resolveLocale } from '../../core/i18n';
import { SearchQueryDto } from './dto/search-query.dto';
import { SearchService } from './search.service';

@Controller('v1/search')
export class SearchController {
  constructor(
    @Inject(SearchService)
    private readonly searchService: SearchService,
  ) {}

  @Get()
  async search(
    @Query() query: SearchQueryDto,
    @Headers('accept-language') acceptLanguage?: string,
  ) {
    const locale = resolveLocale(acceptLanguage);
    return this.searchService.search(query.q, {
      jurisdiction: query.jurisdiction,
      documentType: query.document_type,
      page: query.page,
      pageSize: query.page_size,
      locale,
    });
  }

  @Get('context')
  async getContext(@Headers('accept-language') acceptLanguage?: string) {
    const locale = resolveLocale(acceptLanguage);
    return this.searchService.getContext(locale);
  }
}
