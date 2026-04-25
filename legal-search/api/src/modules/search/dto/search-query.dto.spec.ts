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

  describe('canonical jurisdiction/authority IDs', () => {
    it('returns the parsed canonical jurisdiction IDs (single + CSV merged, deduped)', () => {
      const dto = new SearchQueryDto();
      dto.jurisdiction_id = 'jur_ch_federal';
      dto.jurisdiction_ids = 'jur_ch_zh,jur_ch_federal,garbage';

      expect(dto.getCanonicalJurisdictionIds()).toEqual(['jur_ch_zh', 'jur_ch_federal']);
    });

    it('accepts municipality-level canonical IDs (CH BFS + DE AGS)', () => {
      const dto = new SearchQueryDto();
      dto.jurisdiction_ids = 'jur_ch_gemeinde_4001, jur_de_gemeinde_05111000';
      expect(dto.getCanonicalJurisdictionIds()).toEqual([
        'jur_ch_gemeinde_4001',
        'jur_de_gemeinde_05111000',
      ]);
    });

    it('returns undefined when no canonical jurisdiction params are set', () => {
      const dto = new SearchQueryDto();
      expect(dto.getCanonicalJurisdictionIds()).toBeUndefined();
    });

    it('returns undefined when only invalid tokens are present', () => {
      const dto = new SearchQueryDto();
      dto.jurisdiction_ids = 'CH, garbage, auth_fedlex';
      expect(dto.getCanonicalJurisdictionIds()).toBeUndefined();
    });

    it('parses canonical authority IDs', () => {
      const dto = new SearchQueryDto();
      dto.authority_id = 'auth_fedlex';
      dto.authority_ids = 'auth_de_bgh, auth_fedlex';
      expect(dto.getCanonicalAuthorityIds()).toEqual(['auth_de_bgh', 'auth_fedlex']);
    });

    it('keeps ISO and canonical filters independent so the adapter can AND them server-side', () => {
      const dto = new SearchQueryDto();
      dto.jurisdiction = 'CH';
      dto.jurisdiction_id = 'jur_ch_federal';

      expect(dto.getNormalizedJurisdictions()).toEqual(['ch']);
      expect(dto.getCanonicalJurisdictionIds()).toEqual(['jur_ch_federal']);
    });
  });
});
