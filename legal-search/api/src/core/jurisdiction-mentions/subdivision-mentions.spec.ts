import { describe, expect, it } from 'vitest';
import { detectableSubdivisions, detectSubdivisionMentions } from './subdivision-mentions';

describe('detectSubdivisionMentions', () => {
  describe('the vocabulary it reads', () => {
    it('resolves all 26 Swiss cantons from the subdivisions vocabulary to canonical ids', () => {
      // Not decoration: the whole mechanism is dead if this join breaks, and a
      // dead detector under-refuses SILENTLY. `getJurisdictionBySlug` returning
      // undefined for every canton would drop them all from CANDIDATES and this
      // test is the only thing that would notice.
      const swiss = detectableSubdivisions().filter((entry) => entry.isoCode.startsWith('CH-'));
      expect(swiss).toHaveLength(26);
      expect(swiss.map((entry) => entry.jurisdictionId)).toContain('jur_ch_be');
      expect(swiss.map((entry) => entry.jurisdictionId)).toContain('jur_ch_zh');
    });
  });

  describe('what it detects', () => {
    it('detects a canton named with a German tier marker', () => {
      expect(detectSubdivisionMentions('Hundegesetz Kanton Bern')).toMatchObject([
        { isoCode: 'CH-BE', jurisdictionId: 'jur_ch_be' },
      ]);
    });

    it('detects a canton named with a French tier marker and a filler word', () => {
      expect(detectSubdivisionMentions('droit du bail canton de Berne')).toMatchObject([
        { isoCode: 'CH-BE', jurisdictionId: 'jur_ch_be' },
      ]);
    });

    it('detects a trailing tier marker', () => {
      expect(detectSubdivisionMentions('Mietrecht Aargau (Kanton)')).toMatchObject([
        { isoCode: 'CH-AG', jurisdictionId: 'jur_ch_ag' },
      ]);
    });

    it('detects the ISO code on its own — nobody writes `CH-BE` meaning anything else', () => {
      expect(detectSubdivisionMentions('Hundegesetz CH-BE')).toMatchObject([
        { isoCode: 'CH-BE', jurisdictionId: 'jur_ch_be' },
      ]);
    });

    it('folds umlauts and their ASCII transliterations to one name', () => {
      for (const query of ['Kanton Zürich', 'Kanton Zuerich', 'kanton zurich']) {
        expect(detectSubdivisionMentions(query), query).toMatchObject([{ isoCode: 'CH-ZH' }]);
      }
    });

    it('detects several cantons in one query', () => {
      const found = detectSubdivisionMentions('Kanton Bern und Kanton Zürich');
      expect(found.map((mention) => mention.isoCode).sort()).toEqual(['CH-BE', 'CH-ZH']);
    });
  });

  describe('what it refuses to detect — the over-refusal guard', () => {
    // Each of these would become a FALSE REFUSAL if the marker requirement were
    // dropped, because the corpus holds none of these cantons. That is the
    // failure mode #986 says is worse than the one being fixed.
    it.each([
      ['ich nehme den Zug nach Hause', 'Zug the train, not Kanton Zug'],
      ['Wanderung im Jura', 'Jura the mountain range'],
      ['Mietrecht Bern', 'a bare city/canton name with no tier marker'],
      ['Basel Fasnacht', 'a city name, and not even a full canton label'],
      ['Genf Konvention', 'the Geneva Convention is not a cantonal statute'],
      ['recipe for chocolate cake', 'no jurisdiction at all'],
      ['Anrechnung ausländischer Quellensteuern', 'a topic, no jurisdiction'],
      ['', 'empty query'],
    ])('does not detect a jurisdiction in %j (%s)', (query) => {
      expect(detectSubdivisionMentions(query)).toEqual([]);
    });

    it('does not match a canton name embedded inside a longer word', () => {
      // Guards the tokenizer: substring matching would make "Kanton Bernstein"
      // or "Urin" fire.
      expect(detectSubdivisionMentions('Kanton Bernstein')).toEqual([]);
      expect(detectSubdivisionMentions('Kanton Urintest')).toEqual([]);
    });

    it('does not match half of a hyphenated canton name', () => {
      // "Basel" alone is ambiguous between BS and BL, so neither fires.
      expect(detectSubdivisionMentions('Kanton Basel')).toEqual([]);
      expect(detectSubdivisionMentions('Kanton Basel-Stadt')).toMatchObject([{ isoCode: 'CH-BS' }]);
    });
  });
});
