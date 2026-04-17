import { Type } from 'class-transformer';
import { IsBoolean, IsInt, IsOptional, IsString, Max, Min } from 'class-validator';

import { type ParsedJurisdictionToken, parseJurisdictionList } from './jurisdiction-token';

const REFINEMENT_TYPES = ['terms', 'date_range', 'range', 'toggle', 'text'] as const;

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
  jurisdiction?: string;

  @IsOptional()
  @IsString()
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

  getNormalizedJurisdictions(): string[] | undefined {
    return normalizeCsv(this.jurisdictions) ?? normalizeCsv(this.jurisdiction);
  }

  /**
   * Return the jurisdiction filter parsed into {country, subdivision?}
   * pairs. Used by projection code that needs to route sub-federal
   * scope (e.g. `CH-ZH`) to a different OpenSearch field than the
   * top-level country. Returns [] when no jurisdiction param is set;
   * silently drops malformed tokens.
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
