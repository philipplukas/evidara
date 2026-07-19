import { Controller, Get, Headers, Inject, Query } from '@nestjs/common';
import { resolveLocale } from '../../core/i18n';
import { CoverageService } from './coverage.service';
// biome-ignore lint/style/useImportType: value import so ValidationPipe sees class-validator metadata on CoverageQueryDto
import { CoverageQueryDto } from './dto/coverage-query.dto';

/**
 * Corpus coverage (ADR-0042) — the surface ADR-0033 §2's refusal capability needs.
 *
 * Contract: `contracts/api/legal-search.openapi.yaml` is the source of truth.
 */
@Controller('v1/coverage')
export class CoverageController {
  constructor(
    @Inject(CoverageService)
    private readonly coverageService: CoverageService,
  ) {}

  @Get()
  async getCoverage(
    @Query() query: CoverageQueryDto,
    @Headers('accept-language') acceptLanguage?: string,
  ) {
    return this.coverageService.getCoverage({
      groupBy: query.group_by,
      jurisdictionId: query.jurisdiction_id,
      authorityId: query.authority_id,
      documentType: query.document_type,
      level: query.level,
      inForceAt: query.in_force_at,
      limit: query.limit,
      locale: resolveLocale(acceptLanguage),
    });
  }
}
