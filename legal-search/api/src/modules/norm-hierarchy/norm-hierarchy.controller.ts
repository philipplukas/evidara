import { Controller, Get, Headers, Inject, Param, Query } from '@nestjs/common';
import { resolveLocale } from '../../core/i18n';
import type { NormHierarchyQueryDto } from './dto/norm-hierarchy-query.dto';
import { NormHierarchyService } from './norm-hierarchy.service';

@Controller('v1/norm-hierarchy')
export class NormHierarchyController {
  constructor(
    @Inject(NormHierarchyService)
    private readonly normHierarchyService: NormHierarchyService,
  ) {}

  @Get(':jurisdiction_id')
  async getNormHierarchy(
    @Param('jurisdiction_id') jurisdictionId: string,
    @Query() query: NormHierarchyQueryDto,
    @Headers('accept-language') acceptLanguage?: string,
  ) {
    return this.normHierarchyService.getHierarchy({
      jurisdictionId,
      inForceAt: query.in_force_at,
      limit: query.limit,
      locale: resolveLocale(acceptLanguage),
    });
  }
}
