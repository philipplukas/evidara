import { Inject, Injectable, Logger } from '@nestjs/common';
import type { SupportedLocale } from '../../core/i18n';
import { DEFAULT_LOCALE } from '../../core/i18n';
import {
  detectSubdivisionMentions,
  type SubdivisionMention,
} from '../../core/jurisdiction-mentions';
import { getGoverningScopes } from '../../core/norm-hierarchy';
import type { WarnFn } from '../../core/types/warn';
import { CorpusJurisdictionsService } from './corpus-jurisdictions.service';
import type { SearchRefusalEntity } from './entities/search.entities';
import { mapContextAggregations } from './mappers/search-context.mapper';
import { mapAggregationsToFacets } from './mappers/search-facet.mapper';
import { mapSearchHitToView } from './mappers/search-result.mapper';
import {
  SEARCH_REPOSITORY,
  type SearchRefinement,
  type SearchRepository,
} from './search.repository';

/**
 * Which jurisdictions should a query that NAMES a place prefer? (#975 gap A)
 *
 * The named jurisdiction, plus every scope that governs it — which for a Swiss
 * canton is the federal tier, because `getGoverningScopes` treats a same-level
 * child (`jur_ch_federal` under `jur_ch`) as a refinement of its parent's scope
 * rather than a tier below it. So this is read out of the jurisdiction seed,
 * not hardcoded to Switzerland, and an AT or DE overlay gets the same shape for
 * free.
 *
 * **Including the federal tier is the point, not a detail.** Measured against
 * production 2026-09-19 for "Darf ich in Zürich einen Hund halten": boosting
 * the canton ALONE pushed the federal Tierschutzgesetz from rank 15 out of the
 * top 20 entirely, because every Zurich document gained on it. A cantonal
 * question in Swiss law always has a federal rung above it — ADR-0033's dog
 * question needs both — so burying it to surface the canton answers the
 * question worse, not better. With the chain, it stays at 15.
 *
 * Returns `undefined` when the query names nowhere, which is the overwhelming
 * majority of queries: they are then scored exactly as they are today.
 */
function preferredJurisdictionIds(mentions: SubdivisionMention[]): string[] | undefined {
  if (mentions.length === 0) return undefined;

  const ids = new Set<string>();
  for (const mention of mentions) {
    ids.add(mention.jurisdictionId);
    for (const scope of getGoverningScopes(mention.jurisdictionId)) {
      ids.add(scope.jurisdiction_id);
    }
  }
  return [...ids];
}

@Injectable()
export class SearchService {
  private readonly logger = new Logger(SearchService.name);
  private readonly warn: WarnFn;

  constructor(
    @Inject(SEARCH_REPOSITORY)
    private readonly repository: SearchRepository,
    @Inject(CorpusJurisdictionsService)
    private readonly corpusJurisdictions: CorpusJurisdictionsService,
  ) {
    this.warn = (event, meta) => this.logger.warn(`[contract] ${event}`, meta);
  }

  async search(
    query: string,
    options?: {
      jurisdictions?: string[];
      jurisdictionIds?: string[];
      authorityIds?: string[];
      languages?: string[];
      documentTypes?: string[];
      officialOnly?: boolean;
      refinements?: SearchRefinement[];
      page?: number;
      pageSize?: number;
      locale?: SupportedLocale;
    },
  ) {
    const locale = options?.locale ?? DEFAULT_LOCALE;

    const mentions = detectSubdivisionMentions(query);

    const refusal = await this.refuseIfJurisdictionNotHeld(query, mentions);
    if (refusal) {
      // Deliberately no search round trip. Returning the best-scoring documents
      // of a DIFFERENT canton beside the refusal is exactly the confident wrong
      // answer #986 measured; an agent would cite them.
      return { results: [], facets: [], totalResults: 0, refusal };
    }

    const result = await this.repository.search(query, {
      jurisdictions: options?.jurisdictions,
      jurisdictionIds: options?.jurisdictionIds,
      authorityIds: options?.authorityIds,
      languages: options?.languages,
      documentTypes: options?.documentTypes,
      officialOnly: options?.officialOnly,
      refinements: options?.refinements,
      page: options?.page,
      pageSize: options?.pageSize,
      boostJurisdictionIds: preferredJurisdictionIds(mentions),
    });

    return {
      results: result.hits.map((hit) => mapSearchHitToView(hit, locale, this.warn)),
      facets: mapAggregationsToFacets(result.aggregations, locale),
      totalResults: result.total,
    };
  }

  /**
   * Refusal on coverage grounds (#986) — "I do not hold Bern's dog law" rather
   * than the best-scoring Zurich document.
   *
   * Every step here is written to fail towards ANSWERING. Refusal needs three
   * positive findings at once, and the absence of any one of them means the
   * query is served exactly as it is today:
   *
   *   1. the query NAMES a sub-federal jurisdiction, with a tier marker beside
   *      it — see `core/jurisdiction-mentions` for why a bare name is not
   *      enough (`Zug` is a train, `Zürich` is also a city);
   *   2. the corpus's holdings are KNOWN — an unknown or empty holdings answer
   *      refuses nothing;
   *   3. NONE of the named jurisdictions is held. "Kanton Bern und Kanton
   *      Zürich" against a ZH corpus answers, because one of the two is held
   *      and a partial answer beats no answer.
   *
   * The result is that this can only ever withhold results for a query that
   * positively names a place the index positively does not hold.
   */
  private async refuseIfJurisdictionNotHeld(
    query: string,
    mentions: SubdivisionMention[],
  ): Promise<SearchRefusalEntity | undefined> {
    if (mentions.length === 0) return undefined;

    const held = await this.corpusJurisdictions.heldJurisdictionIds();
    // `undefined` is "we could not find out", never "we hold nothing". The
    // empty-buckets case is folded into it there, deliberately in ONE place:
    // enforcing the same rule again here would leave two answers to the same
    // question and no way to tell which one is the policy.
    if (!held) return undefined;

    const unheld = mentions.filter((mention) => !held.has(mention.jurisdictionId));
    if (unheld.length !== mentions.length) return undefined;

    this.logger.log(
      `refusing "${query}": corpus holds no documents for ${unheld
        .map((mention) => mention.jurisdictionId)
        .join(', ')}`,
    );
    return {
      code: 'jurisdiction_not_held',
      message: this.refusalMessage(unheld),
      jurisdictions: unheld.map((mention) => ({
        jurisdiction_id: mention.jurisdictionId,
        iso_code: mention.isoCode,
        label: mention.label,
        holding: 'not_held' as const,
      })),
    };
  }

  private refusalMessage(unheld: SubdivisionMention[]): string {
    const names = unheld.map((mention) => `${mention.label} (${mention.isoCode})`).join(', ');
    return (
      `This search was not answered: the corpus holds no documents for ${names}. ` +
      'That is a statement about what has been acquired and processed, not about ' +
      'whether the law exists. Results from another jurisdiction are withheld ' +
      'deliberately rather than presented as an answer.'
    );
  }

  async getContext(locale: SupportedLocale = DEFAULT_LOCALE) {
    const aggs = await this.repository.getContextAggregations();
    return mapContextAggregations(aggs, locale);
  }
}
