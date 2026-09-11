import { Inject, Injectable, Logger } from '@nestjs/common';
import type { SupportedLocale } from '../../core/i18n';
import { DEFAULT_LOCALE } from '../../core/i18n';
import {
  detectSubdivisionMentions,
  type SubdivisionMention,
} from '../../core/jurisdiction-mentions';
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

    const refusal = await this.refuseIfJurisdictionNotHeld(query);
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
  ): Promise<SearchRefusalEntity | undefined> {
    const mentions = detectSubdivisionMentions(query);
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
