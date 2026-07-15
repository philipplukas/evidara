/**
 * `norm_hierarchy(jurisdiction_id)` — what governs this place, at each level.
 *
 * One of ADR-0033's six MCP tools, and the one that turns "can the city ban a
 * certain thing for dogs, year-round?" from a retrieval question into a
 * traversal. The answer is not a ranked list of similar text; it is the ordered
 * set of legal orders that bind the place — constitutional, federal, cantonal,
 * municipal — and the norms we actually hold at each.
 *
 * The `coverage` block is not decoration. ADR-0033 §2: the agent must be able to
 * refuse. If we hold no municipal ordinance for Zurich, the correct answer is "I
 * do not have the Hundereglement for this commune", and this endpoint is where
 * that is knowable — a level that is expected but empty is reported as missing
 * rather than quietly omitted, so an agent cannot mistake absence for licence to
 * reason from the next-best text.
 */
import { Inject, Injectable, NotFoundException } from '@nestjs/common';
import type { SupportedLocale } from '../../core/i18n/locale';
import {
  getJurisdiction,
  getNormHierarchyLevels,
  normLevelLabel,
  resolveInForceState,
} from '../../core/norm-hierarchy';
import type { NormHierarchyView } from './entities/norm-hierarchy.entities';
import {
  NORM_HIERARCHY_REPOSITORY,
  type NormHierarchyRepository,
} from './norm-hierarchy.repository';

/** Norms shown per level. A hierarchy walk is a briefing, not a search page. */
const DEFAULT_PER_LEVEL_LIMIT = 10;
const MAX_PER_LEVEL_LIMIT = 50;

export type NormHierarchyQuery = {
  jurisdictionId: string;
  inForceAt?: string;
  limit?: number;
  locale?: SupportedLocale;
};

@Injectable()
export class NormHierarchyService {
  constructor(
    @Inject(NORM_HIERARCHY_REPOSITORY)
    private readonly repository: NormHierarchyRepository,
  ) {}

  async getHierarchy(query: NormHierarchyQuery): Promise<NormHierarchyView> {
    const jurisdiction = getJurisdiction(query.jurisdictionId);
    const levels = getNormHierarchyLevels(query.jurisdictionId);
    if (!jurisdiction || levels.length === 0) {
      throw new NotFoundException(`Jurisdiction ${query.jurisdictionId} not found`);
    }

    const perLevelLimit = Math.min(
      Math.max(query.limit ?? DEFAULT_PER_LEVEL_LIMIT, 1),
      MAX_PER_LEVEL_LIMIT,
    );
    const scopeIds = [...new Set(levels.flatMap((level) => level.jurisdictionIds))];

    const found = await this.repository.findNormsByScopes({
      jurisdictionIds: scopeIds,
      inForceAt: query.inForceAt,
      perLevelLimit,
    });

    const locale = query.locale ?? 'en';
    const levelViews = levels.map((level) => {
      const documents = found.documents.get(level.level) ?? [];
      return {
        level: level.level,
        rank: level.rank,
        label: normLevelLabel(level.level, locale),
        jurisdiction_ids: level.jurisdictionIds,
        total: found.totals.get(level.level) ?? 0,
        documents: documents.map((document) => ({
          document_id: document.document_id,
          title: document.title,
          document_type: document.document_type,
          official_citation: document.official_citation,
          jurisdiction_ids: document.jurisdiction_ids,
          effective_date: document.effective_date,
          in_force_from: document.in_force_from,
          in_force_until: document.in_force_until,
          in_force_state: query.inForceAt
            ? resolveInForceState(document, query.inForceAt)
            : undefined,
        })),
      };
    });

    return {
      jurisdiction: {
        jurisdiction_id: jurisdiction.jurisdiction_id,
        name: jurisdiction.name,
        slug: jurisdiction.slug,
        level: jurisdiction.level,
      },
      in_force_at: query.inForceAt,
      levels: levelViews,
      coverage: {
        covered_levels: levelViews.filter((l) => l.total > 0).map((l) => l.level),
        // The levels that bind this place but for which we hold nothing. An
        // agent that reasons past a missing level is fabricating.
        missing_levels: levelViews.filter((l) => l.total === 0).map((l) => l.level),
      },
    };
  }
}
