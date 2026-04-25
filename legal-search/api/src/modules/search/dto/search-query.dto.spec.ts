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

  it('returns undefined for malformed official_only values', () => {
    const dto = new SearchQueryDto();
    dto.official_only = 'yes' as unknown as boolean;
    expect(dto.getOfficialOnly()).toBeUndefined();
  });

  describe('canonical jurisdiction routing', () => {
    it('splits ISO and canonical tokens into two helper outputs', () => {
      const dto = new SearchQueryDto();
      dto.jurisdictions = 'CH-ZH, jur_ch_gemeinde_261, DE';

      expect(dto.getNormalizedJurisdictions()).toEqual(['ch-zh', 'de']);
      expect(dto.getCanonicalJurisdictionIds()).toEqual(['jur_ch_gemeinde_261']);
    });

    it('returns undefined for canonical ids when only ISO tokens are present', () => {
      const dto = new SearchQueryDto();
      dto.jurisdictions = 'CH, AT';

      expect(dto.getNormalizedJurisdictions()).toEqual(['ch', 'at']);
      expect(dto.getCanonicalJurisdictionIds()).toBeUndefined();
    });

    it('returns undefined for ISO tokens when only canonical ids are present', () => {
      const dto = new SearchQueryDto();
      dto.jurisdictions = 'jur_ch_federal,jur_de_05315000';

      expect(dto.getNormalizedJurisdictions()).toBeUndefined();
      expect(dto.getCanonicalJurisdictionIds()).toEqual([
        'jur_ch_federal',
        'jur_de_05315000',
      ]);
    });

    it('falls back to the singular `jurisdiction` field when `jurisdictions` is unset', () => {
      const dto = new SearchQueryDto();
      dto.jurisdiction = 'jur_ch_federal';

      expect(dto.getCanonicalJurisdictionIds()).toEqual(['jur_ch_federal']);
    });

    it('returns undefined for both helpers when no jurisdiction param is set', () => {
      const dto = new SearchQueryDto();

      expect(dto.getNormalizedJurisdictions()).toBeUndefined();
      expect(dto.getCanonicalJurisdictionIds()).toBeUndefined();
    });
  });
});
