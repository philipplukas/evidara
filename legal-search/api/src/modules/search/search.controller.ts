import { Controller, Get, Query } from '@nestjs/common';
import { ApiBearerAuth, ApiOperation, ApiTags } from '@nestjs/swagger';
import type { SearchQueryDto } from './dto/search-query.dto';
import type { SearchResponseDto } from './dto/search-response.dto';
import type { SearchService } from './search.service';

/**
 * TODO: Wire a JWT AuthGuard once the auth provider is configured.
 * The @ApiBearerAuth decorator below is documentation-only and does NOT
 * enforce token validation at runtime.
 */
@ApiTags('search')
@ApiBearerAuth()
@Controller('v1/search')
export class SearchController {
  constructor(private readonly searchService: SearchService) {}

  @Get()
  @ApiOperation({
    operationId: 'searchDocuments',
    summary: 'Search documents',
  })
  async search(@Query() query: SearchQueryDto): Promise<SearchResponseDto> {
    return this.searchService.search(query);
  }
}
