/**
 * `GET /v1/coverage` — what the corpus holds for a named scope (ADR-0042).
 *
 * ADR-0033 §2 calls explicit coverage "the only real cure for confident
 * fabrication": an agent that can check whether the governing norm is in the
 * corpus can refuse instead of reaching for the nearest plausible text. Before
 * this endpoint the only signal about absence was `totalResults: 0`, which
 * conflates "we do not hold it", "the query missed it", "a filter bug dropped
 * it" (#672 did exactly this) and "it does not exist".
 *
 * Three rules carry the honesty of this module, and each is enforced below:
 *
 *  1. **Absence is reported, never inferred.** A jurisdiction the caller names
 *     explicitly always comes back as a group — with `documents: 0,
 *     holding: not_held` when we hold nothing. That is a positive statement of
 *     what we do not have, which is the whole point of #709.
 *
 *  2. **`not_held` is about the corpus, never about the law.** It means the
 *     index contains no matching document. It is not evidence the norm does not
 *     exist. The `CoverageHolding` union has exactly two members so no caller
 *     can find a value that means "confirmed absent in law".
 *
 *  3. **An unrecognized id is not a coverage answer.** A jurisdiction id the
 *     platform does not know produces NO group and is listed in
 *     `unrecognized_jurisdiction_ids`. Returning `not_held` for a typo would
 *     answer a coverage question that was never asked.
 */
import { BadRequestException, Inject, Injectable } from '@nestjs/common';
import { DEFAULT_LOCALE, type SupportedLocale } from '../../core/i18n/locale';
import {
  getJurisdiction,
  isNormLevel,
  type NormLevel,
  normLevelLabel,
} from '../../core/norm-hierarchy';
import { type CoverageDimension, isCoverageDimension } from '../../core/opensearch/facet-fields';
import { COVERAGE_REPOSITORY, type CoverageRepository } from './coverage.repository';
import type {
  CorpusCoverageView,
  CoverageGroup,
  CoverageScope,
} from './entities/coverage.entities';

const DEFAULT_LIMIT = 100;
const MAX_LIMIT = 1000;
const DEFAULT_DIMENSION: CoverageDimension = 'jurisdiction';
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export type CoverageQuery = {
  groupBy?: string;
  jurisdictionId?: string;
  authorityId?: string;
  documentType?: string;
  level?: string;
  inForceAt?: string;
  limit?: number;
  locale?: SupportedLocale;
};

/** Split a comma-separated query parameter, dropping blanks. */
function parseCsv(value: string | undefined): string[] | undefined {
  if (!value) return undefined;
  const parts = value
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean);
  return parts.length ? [...new Set(parts)] : undefined;
}

@Injectable()
export class CoverageService {
  constructor(
    @Inject(COVERAGE_REPOSITORY)
    private readonly repository: CoverageRepository,
  ) {}

  async getCoverage(query: CoverageQuery): Promise<CorpusCoverageView> {
    const dimension = this.resolveDimension(query.groupBy);
    const levels = this.resolveLevels(query.level);
    const inForceAt = this.resolveInForceAt(query.inForceAt);
    const limit = Math.min(Math.max(query.limit ?? DEFAULT_LIMIT, 1), MAX_LIMIT);
    // `'en'` is not a supported locale (`SUPPORTED_LOCALES` is de/fr), so fall
    // back to the declared default rather than inventing one.
    const locale = query.locale ?? DEFAULT_LOCALE;

    const requestedJurisdictionIds = parseCsv(query.jurisdictionId);
    const authorityIds = parseCsv(query.authorityId);
    const documentTypes = parseCsv(query.documentType);

    // Rule 3: separate ids we do not recognize from ids we hold nothing for.
    // These are different answers and must not be merged.
    const knownJurisdictionIds = requestedJurisdictionIds?.filter((id) => !!getJurisdiction(id));
    const unrecognized = requestedJurisdictionIds?.filter((id) => !getJurisdiction(id));

    const counts = await this.repository.countCoverage({
      dimension,
      // Filtering on the unrecognized ids too would be harmless but pointless;
      // filtering on NONE of them when every requested id is unknown would
      // silently widen the scope to the whole corpus, so an empty known-list
      // must still filter (and match nothing).
      jurisdictionIds: requestedJurisdictionIds ? (knownJurisdictionIds ?? []) : undefined,
      authorityIds,
      documentTypes,
      levels,
      inForceAt,
      limit,
    });

    const held = new Map(counts.buckets.map((bucket) => [bucket.key, bucket]));

    // Rule 1: every explicitly requested key gets a group, held or not. An
    // aggregation only produces buckets for values present in the index, so
    // without this a caller asking about `jur_ch_zh` would get an empty list
    // and be back to inferring absence from emptiness.
    const requestedKeys = this.requestedKeysFor(dimension, {
      jurisdiction: knownJurisdictionIds,
      authority: authorityIds,
      document_type: documentTypes,
      level: levels,
    });

    const groups: CoverageGroup[] = [];
    for (const key of [...new Set([...(requestedKeys ?? []), ...held.keys()])]) {
      const bucket = held.get(key);
      groups.push({
        key,
        label: this.labelFor(dimension, key, locale),
        documents: bucket?.documents ?? 0,
        // Rule 2. `not_held` = the index holds nothing matching this scope.
        // Never a claim about whether the law exists.
        holding: bucket && bucket.documents > 0 ? 'held' : 'not_held',
        last_processed_at: bucket?.lastProcessedAt,
        documents_without_repeal_date: bucket?.documentsWithoutRepealDate ?? 0,
        source_version_ids: bucket?.sourceVersionIds.length ? bucket.sourceVersionIds : undefined,
        source_version_count: bucket?.sourceVersionCount || undefined,
      });
    }
    groups.sort((a, b) => b.documents - a.documents || a.key.localeCompare(b.key));

    const scope: CoverageScope = {
      jurisdiction_ids: requestedJurisdictionIds,
      authority_ids: authorityIds,
      document_types: documentTypes,
      levels,
      in_force_at: inForceAt,
    };

    return {
      basis: 'index',
      as_of: new Date().toISOString(),
      group_by: dimension,
      scope,
      total_documents: counts.totalDocuments,
      documents_without_group_key: counts.documentsWithoutGroupKey,
      unrecognized_jurisdiction_ids: unrecognized?.length ? unrecognized : undefined,
      groups,
    };
  }

  private resolveDimension(groupBy: string | undefined): CoverageDimension {
    if (groupBy === undefined || groupBy === '') return DEFAULT_DIMENSION;
    if (!isCoverageDimension(groupBy)) {
      throw new BadRequestException(`Unknown \`group_by\`: ${groupBy}`);
    }
    return groupBy;
  }

  private resolveLevels(level: string | undefined): NormLevel[] | undefined {
    const parsed = parseCsv(level);
    if (!parsed) return undefined;
    // Reject rather than silently drop: an unknown level quietly ignored would
    // widen the scope, and the caller would read the wider answer as the
    // narrower one they asked for.
    const unknown = parsed.filter((entry) => !isNormLevel(entry));
    if (unknown.length) {
      throw new BadRequestException(`Unknown norm level(s): ${unknown.join(', ')}`);
    }
    return parsed as NormLevel[];
  }

  private resolveInForceAt(inForceAt: string | undefined): string | undefined {
    if (!inForceAt) return undefined;
    if (!ISO_DATE.test(inForceAt) || Number.isNaN(Date.parse(inForceAt))) {
      throw new BadRequestException('`in_force_at` must be an ISO date (YYYY-MM-DD)');
    }
    return inForceAt;
  }

  private requestedKeysFor(
    dimension: CoverageDimension,
    requested: Record<CoverageDimension, string[] | undefined>,
  ): string[] | undefined {
    return requested[dimension];
  }

  private labelFor(
    dimension: CoverageDimension,
    key: string,
    locale: SupportedLocale,
  ): string | undefined {
    // Only jurisdictions and levels have a vocabulary behind them. For
    // authorities and document types no label is known, and `undefined` says so
    // — echoing `key` back as a label would dress an id up as a name.
    if (dimension === 'jurisdiction') return getJurisdiction(key)?.name;
    if (dimension === 'level') return isNormLevel(key) ? normLevelLabel(key, locale) : undefined;
    return undefined;
  }
}
