import { Type } from 'class-transformer';
import { IsBoolean, IsInt, IsOptional, IsString, Matches, Max, Min } from 'class-validator';

import {
  type ParsedJurisdictionToken,
  parseJurisdictionList,
  partitionJurisdictionTokens,
} from './jurisdiction-token';

const REFINEMENT_TYPES = ['terms', 'date_range', 'range', 'toggle', 'text'] as const;

/**
 * Single-token jurisdiction pattern. Matches the OpenAPI contract for the
 * `jurisdiction` query parameter: ISO 3166-1 alpha-2 country, ISO 3166-2
 * subdivision, or a canonical platform-control id (`jur_*`). Case-insensitive
 * — the parser normalizes case before downstream use.
 */
const JURISDICTION_TOKEN_PATTERN =
  /^([A-Za-z]{2}(?:-[A-Za-z0-9]{1,3})?|[Jj][Uu][Rr]_[A-Za-z0-9_]+)$/;

/**
 * CSV-form pattern for the `jurisdictions` query parameter. Same shape as
 * `JURISDICTION_TOKEN_PATTERN` but allows comma-separated tokens with optional
 * surrounding whitespace.
 */
const JURISDICTION_LIST_PATTERN =
  /^\s*([A-Za-z]{2}(?:-[A-Za-z0-9]{1,3})?|[Jj][Uu][Rr]_[A-Za-z0-9_]+)(\s*,\s*([A-Za-z]{2}(?:-[A-Za-z0-9]{1,3})?|[Jj][Uu][Rr]_[A-Za-z0-9_]+))*\s*$/;

type SearchRefinementDto = {
  field: string;
  type: (typeof REFINEMENT_TYPES)[number];
  values: string[];
  from?: string;
  to?: string;
  value?: boolean | string;
};

function normalizeCsv(raw: unknown): string[] | undefined {
  if (typeof raw !== 'string') return undefined;
  return raw
    .split(',')
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
}

function parseRefinements(raw: unknown): SearchRefinementDto[] | undefined {
  if (typeof raw !== 'string') return undefined;
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return undefined;
    return parsed
      .filter((candidate): candidate is SearchRefinementDto => {
        if (typeof candidate !== 'object' || candidate === null) return false;
        const maybe = candidate as Partial<SearchRefinementDto>;
        return (
          typeof maybe.field === 'string' &&
          typeof maybe.type === 'string' &&
          REFINEMENT_TYPES.includes(maybe.type as (typeof REFINEMENT_TYPES)[number]) &&
          Array.isArray(maybe.values)
        );
      })
      .map((refinement) => ({
        ...refinement,
        field: refinement.field.toLowerCase(),
        values: refinement.values
          .map((value) => value.toLowerCase().trim())
          .filter((value) => value.length > 0),
      }));
  } catch {
    return undefined;
  }
}

function parseBoolean(raw: unknown): boolean | undefined {
  if (typeof raw !== 'string') return undefined;
  if (raw === 'true') return true;
  if (raw === 'false') return false;
  return undefined;
}

export class SearchQueryDto {
  @IsString()
  q!: string;

  @IsOptional()
  @IsString()
  @Matches(JURISDICTION_TOKEN_PATTERN, {
    message:
      'jurisdiction must be an ISO 3166-1 country code (e.g. CH), an ISO 3166-2 subdivision code (e.g. CH-ZH), or a canonical jurisdiction id (e.g. jur_ch_federal)',
  })
  jurisdiction?: string;

  @IsOptional()
  @IsString()
  @Matches(JURISDICTION_LIST_PATTERN, {
    message:
      'jurisdictions must be a comma-separated list of ISO country/subdivision codes or canonical jur_* ids',
  })
  jurisdictions?: string;

  @IsOptional()
  @IsString()
  languages?: string;

  @IsOptional()
  @IsString()
  document_type?: string;

  @IsOptional()
  @IsString()
  document_types?: string;

  @IsOptional()
  @Type(() => Boolean)
  @IsBoolean()
  official_only?: boolean;

  @IsOptional()
  @Type(() => String)
  refinements?: string;

  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  page?: number = 1;

  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  @Max(100)
  page_size?: number = 20;

  /**
   * Return the ISO-shape (country / subdivision) tokens only, lowercased.
   * Backwards-compatible with callers that don't yet route canonical
   * `jur_*` ids — those are silently dropped from this list. New code
   * should prefer `getParsedJurisdictions()` plus
   * `partitionJurisdictionTokens()` (or `getCanonicalJurisdictionIds()`)
   * to also surface the canonical-id route.
   */
  getNormalizedJurisdictions(): string[] | undefined {
    const parsed = this.getParsedJurisdictions();
    if (parsed.length === 0) {
      // Preserve historical behavior: empty/missing param -> undefined,
      // not [], so the adapter skips the filter entirely.
      return undefined;
    }
    const { isoTokens } = partitionJurisdictionTokens(parsed);
    return isoTokens.length > 0 ? isoTokens : undefined;
  }

  /**
   * Return the canonical `jur_*` jurisdiction ids parsed from the query
   * param. The adapter routes these to `jurisdiction_ids.keyword` (the
   * multi-valued projection field added by the canonical-ID slice; see
   * #425). Returns undefined when no canonical ids were supplied so the
   * adapter skips the filter entirely.
   */
  getCanonicalJurisdictionIds(): string[] | undefined {
    const parsed = this.getParsedJurisdictions();
    if (parsed.length === 0) return undefined;
    const { canonicalIds } = partitionJurisdictionTokens(parsed);
    return canonicalIds.length > 0 ? canonicalIds : undefined;
  }

  /**
   * Return the jurisdiction filter parsed into discriminated tokens
   * (ISO country, ISO subdivision, or canonical id). Used by projection
   * code that needs to route sub-federal scope (e.g. `CH-ZH`) or
   * canonical ids (e.g. `jur_ch_federal`) to the right OpenSearch field.
   * Returns [] when no jurisdiction param is set; silently drops
   * malformed tokens.
   */
  getParsedJurisdictions(): ParsedJurisdictionToken[] {
    if (typeof this.jurisdictions === 'string' && this.jurisdictions.trim() !== '') {
      return parseJurisdictionList(this.jurisdictions);
    }
    if (typeof this.jurisdiction === 'string' && this.jurisdiction.trim() !== '') {
      return parseJurisdictionList(this.jurisdiction);
    }
    return [];
  }

  getNormalizedLanguages(): string[] | undefined {
    return normalizeCsv(this.languages);
  }

  getNormalizedDocumentTypes(): string[] | undefined {
    const fromMany = normalizeCsv(this.document_types)?.filter((value) => value !== 'all');
    if (fromMany && fromMany.length > 0) return fromMany;
    return normalizeCsv(this.document_type)?.filter((value) => value !== 'all');
  }

  getOfficialOnly(): boolean | undefined {
    if (typeof this.official_only === 'boolean') {
      return this.official_only;
    }
    return parseBoolean(this.official_only);
  }

  getRefinements(): SearchRefinementDto[] {
    return parseRefinements(this.refinements) ?? [];
  }
}
