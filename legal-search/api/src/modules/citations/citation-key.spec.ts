import { describe, expect, it } from 'vitest';
import { normalizeCitationText, parseCitationKey } from './citation-key';

/**
 * These keys are a CONTRACT with document-intelligence's `normalize_citation()`
 * (`nlp/citation_extractor.py`). DI writes them onto citation rows; this module
 * produces them from user/agent input. If the two drift, the join silently
 * yields nothing and the graph loses edges with no error anywhere — so the
 * exact key strings are pinned here.
 */
describe('normalizeCitationText', () => {
  describe('deterministic types (the ones DI keys)', () => {
    it('keys a Swiss SR number, the authoritative id for federal law', () => {
      expect(normalizeCitationText('SR 210')).toBe('sr:210');
      expect(normalizeCitationText('SR 311.0')).toBe('sr:311.0');
      // Appearing inside prose, as it does in a real citation.
      expect(normalizeCitationText('Ergaenzend gilt das ZGB (SR 210).')).toBe('sr:210');
    });

    it('keys a CELEX number', () => {
      expect(normalizeCitationText('32016R0679')).toBe('celex:32016R0679');
    });

    it('keys prose EU references to CELEX, zero-padding the ordinal like DI', () => {
      expect(normalizeCitationText('Regulation (EU) 2016/679')).toBe('celex:32016R0679');
      expect(normalizeCitationText('Directive 2016/680')).toBe('celex:32016L0680');
    });

    it('declines a two-digit-year directive, exactly as DI does', () => {
      // DI's normalize_citation requires a 4-digit year (`(\d{4})/(\d{1,4})`),
      // so "Directive 95/46/EC" yields no key there either. Minting one HERE
      // would invent an edge DI never wrote — the two sides must agree, or the
      // join produces phantom matches.
      expect(normalizeCitationText('Directive 95/46/EC')).toBeNull();
    });

    it('keys an ECLI', () => {
      expect(normalizeCitationText('ECLI:CH:BGER:2023:1C.123.2022')).toBe(
        'ecli:ECLI:CH:BGER:2023:1C.123.2022',
      );
    });

    it('keys an Austrian BGBl reference', () => {
      expect(normalizeCitationText('BGBl. I Nr. 43/1975')).toBe('at_bgbl:43/1975');
    });
  });

  describe('canonical keys pass through', () => {
    it('accepts a key that is already canonical', () => {
      expect(normalizeCitationText('sr:210')).toBe('sr:210');
      expect(normalizeCitationText('celex:32016R0679')).toBe('celex:32016R0679');
    });
  });

  describe('fuzzy types are reported, never guessed', () => {
    // The honesty requirement (ADR-0032): a citation we cannot key is a broken
    // edge, and it must surface as such. Returning a plausible norm here would
    // be the exact "confidently wrong" failure ADR-0033 exists to prevent.
    it.each([
      ['BGE 145 I 73', 'Swiss case reporter citation'],
      ['§ 823 BGB', 'German statute paragraph'],
      ['', 'empty input'],
      ['   ', 'whitespace only'],
    ])('returns null for %s (%s)', (input) => {
      expect(normalizeCitationText(input)).toBeNull();
    });
  });

  describe('article references (#594)', () => {
    // These MUST stay byte-identical to `normalize_citation`'s output in
    // `nlp/citation_extractor.py`. Drift here silently loses edges, which is
    // why the keys are asserted literally rather than via a shared helper.
    it('keys an article reference by short title and article number', () => {
      expect(normalizeCitationText('Art. 36 BV')).toBe('abbrev_art:BV/36');
      expect(normalizeCitationText('Art. 754 OR')).toBe('abbrev_art:OR/754');
      expect(normalizeCitationText('Art. 261bis StGB')).toBe('abbrev_art:StGB/261bis');
    });

    it('ignores Abs./lit. — the article is the addressable unit', () => {
      expect(normalizeCitationText('Art. 36 Abs. 2 BV')).toBe('abbrev_art:BV/36');
      expect(normalizeCitationText('Art. 36 Abs. 2 lit. a BV')).toBe('abbrev_art:BV/36');
    });

    it('refuses a trailing word that is not abbreviation-shaped', () => {
      // The BV's own headings. Keying these is how 187 phantom citations got
      // into the graph; a ranking resolver would have turned each into an edge.
      expect(normalizeCitationText('Art. 36 Einschränkungen')).toBeNull();
      expect(normalizeCitationText('Art. 1 Schweizerische')).toBeNull();
      expect(normalizeCitationText('Art. 2 Zweck')).toBeNull();
    });
  });
});

describe('parseCitationKey', () => {
  it('splits a canonical key into its parts', () => {
    expect(parseCitationKey('sr:210')).toEqual({ identifierType: 'sr', identifierValue: '210' });
  });

  it('keeps the full ECLI as the value, matching DI (ecli:ECLI:...)', () => {
    expect(parseCitationKey('ecli:ECLI:CH:BGER:2023:1C.123.2022')).toEqual({
      identifierType: 'ecli',
      identifierValue: 'ECLI:CH:BGER:2023:1C.123.2022',
    });
  });

  it('rejects strings that are not keys of a type we mint', () => {
    expect(parseCitationKey('SR 210')).toBeNull();
    expect(parseCitationKey('nonsense:1')).toBeNull();
    expect(parseCitationKey('sr:')).toBeNull();
    expect(parseCitationKey(':210')).toBeNull();
  });
});
