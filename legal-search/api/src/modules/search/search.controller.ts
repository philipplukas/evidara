import { Controller, Get, Headers, Inject, Query } from '@nestjs/common';
import { resolveLocale } from '../../core/i18n';
// biome-ignore lint/style/useImportType: value import so ValidationPipe sees class-validator metadata on SearchQueryDto
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
      jurisdictions: query.getNormalizedJurisdictions(),
      jurisdictionIds: query.getCanonicalJurisdictionIds(),
      authorityIds: query.getCanonicalAuthorityIds(),
      languages: query.getNormalizedLanguages(),
      documentTypes: query.getNormalizedDocumentTypes(),
      officialOnly: query.getOfficialOnly(),
      refinements: query.getRefinements(),
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
