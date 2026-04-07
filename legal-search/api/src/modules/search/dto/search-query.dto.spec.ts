import 'reflect-metadata';
import { describe, expect, it } from 'vitest';
import { SearchQueryDto } from './search-query.dto';

describe('SearchQueryDto', () => {
  it('normalizes csv context filters and strips unsupported source type token', () => {
    const dto = new SearchQueryDto();
    dto.jurisdictions = 'CH, at';
    dto.languages = 'de, FR';
    dto.document_types = 'law,all,decision';

    expect(dto.getNormalizedJurisdictions()).toEqual(['ch', 'at']);
    expect(dto.getNormalizedLanguages()).toEqual(['de', 'fr']);
    expect(dto.getNormalizedDocumentTypes()).toEqual(['law', 'decision']);
  });

  it('parses refinement payload and rejects malformed values', () => {
    const dto = new SearchQueryDto();
    dto.refinements = JSON.stringify([
      { field: 'court_level', type: 'terms', values: [' Supreme ', 'cantonal'] },
      { field: 'ignored', type: 'unknown', values: ['x'] },
      { field: 123, type: 'terms', values: ['x'] },
    ]);

    expect(dto.getRefinements()).toEqual([
      { field: 'court_level', type: 'terms', values: ['supreme', 'cantonal'] },
    ]);
  });

  it('parses official_only from both boolean and string values', () => {
    const dto = new SearchQueryDto();
    dto.official_only = true;
    expect(dto.getOfficialOnly()).toBe(true);

    const dtoStringTrue = new SearchQueryDto();
    dtoStringTrue.official_only = 'true' as unknown as boolean;
    expect(dtoStringTrue.getOfficialOnly()).toBe(true);

    const dtoStringFalse = new SearchQueryDto();
    dtoStringFalse.official_only = 'false' as unknown as boolean;
    expect(dtoStringFalse.getOfficialOnly()).toBe(false);
  });
});
