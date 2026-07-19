import { Controller, Get, Headers, Inject, Param, Query } from '@nestjs/common';
import { resolveLocale } from '../../core/i18n';
// Value import, deliberately: `import type` erases the class, and ValidationPipe
// then has no metatype to instantiate — it hands the handler an empty object and
// `in_force_at` silently stops applying (#728). Guarded by
// `scripts/check-validation-metadata.mjs` against the compiled output.
import { NormHierarchyQueryDto } from './dto/norm-hierarchy-query.dto';
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
