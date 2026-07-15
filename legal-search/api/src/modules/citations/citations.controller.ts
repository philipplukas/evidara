import { BadRequestException, Controller, Get, Inject, Query } from '@nestjs/common';
import { CitationsService } from './citations.service';

/**
 * Citation-graph traversal endpoints (ADR-0033 steps 3-4).
 *
 * Contract: `contracts/api/legal-search.openapi.yaml` is the source of truth
 * for these paths; the shapes here follow it.
 */
@Controller('v1/citations')
export class CitationsController {
  constructor(
    @Inject(CitationsService)
    private readonly citationsService: CitationsService,
  ) {}

  /** `resolve_citation` — citation string or canonical key -> the norm it points to. */
  @Get('resolve')
  async resolve(@Query('q') q?: string) {
    const query = q?.trim();
    if (!query) throw new BadRequestException('query parameter `q` is required');
    return this.citationsService.resolve(query);
  }

  /** `find_citing` — norm (document id or citation key) -> what cites it. */
  @Get('citing')
  async citing(@Query('q') q?: string, @Query('limit') limit?: string) {
    const query = q?.trim();
    if (!query) throw new BadRequestException('query parameter `q` is required');

    const parsedLimit = limit === undefined ? undefined : Number.parseInt(limit, 10);
    if (parsedLimit !== undefined && (Number.isNaN(parsedLimit) || parsedLimit < 1)) {
      throw new BadRequestException('`limit` must be a positive integer');
    }
    return this.citationsService.findCiting(query, Math.min(parsedLimit ?? 50, 200));
  }

  /**
   * Corpus-wide resolution rate — how much of the citation graph actually
   * resolves to edges. Reported honestly, including the unresolved breakdown.
   */
  @Get('stats')
  async stats() {
    return this.citationsService.getStats();
  }
}
