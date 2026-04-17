/**
 * Jurisdiction-token parser tests.
 *
 * WHY THIS TEST EXISTS:
 * The OpenAPI contract (T5.2) accepts either country codes (`CH`) or
 * subdivision codes (`CH-ZH`) in the `jurisdiction` query param. A typo
 * like `ch-zh` (lowercased) or `chzh` (no delimiter) must not silently
 * slip through as a valid token — the parser owns that gate.
 */

import { describe, expect, it } from 'vitest';
import { parseJurisdictionList, parseJurisdictionToken } from './jurisdiction-token';

describe('parseJurisdictionToken', () => {
  it('parses a plain country code', () => {
    expect(parseJurisdictionToken('CH')).toEqual({ country: 'CH' });
  });

  it('parses a subdivision code and preserves the full ISO 3166-2 form', () => {
    expect(parseJurisdictionToken('CH-ZH')).toEqual({
      country: 'CH',
      subdivision: 'CH-ZH',
    });
  });

  it('normalizes lowercased input to uppercase', () => {
    expect(parseJurisdictionToken('ch-zh')).toEqual({
      country: 'CH',
      subdivision: 'CH-ZH',
    });
    expect(parseJurisdictionToken('de')).toEqual({ country: 'DE' });
  });

  it('trims surrounding whitespace', () => {
    expect(parseJurisdictionToken('  IT-25  ')).toEqual({
      country: 'IT',
      subdivision: 'IT-25',
    });
  });

  it('handles numeric-suffix subdivisions (IT regioni, AT Bundesländer)', () => {
    expect(parseJurisdictionToken('IT-25')?.subdivision).toBe('IT-25');
    expect(parseJurisdictionToken('AT-9')?.subdivision).toBe('AT-9');
  });

  it('rejects malformed tokens', () => {
    expect(parseJurisdictionToken('')).toBeNull();
    expect(parseJurisdictionToken('CHH')).toBeNull();
    expect(parseJurisdictionToken('CH-')).toBeNull();
    expect(parseJurisdictionToken('CHZH')).toBeNull();
    expect(parseJurisdictionToken('CH-ZH-XX')).toBeNull();
    expect(parseJurisdictionToken('CH ZH')).toBeNull();
    expect(parseJurisdictionToken('C1')).toBeNull();
  });

  it('rejects non-string input defensively', () => {
    expect(parseJurisdictionToken(undefined as unknown as string)).toBeNull();
    expect(parseJurisdictionToken(null as unknown as string)).toBeNull();
    expect(parseJurisdictionToken(42 as unknown as string)).toBeNull();
  });
});

describe('parseJurisdictionList', () => {
  it('returns an empty list for undefined', () => {
    expect(parseJurisdictionList(undefined)).toEqual([]);
  });

  it('parses comma-separated strings', () => {
    expect(parseJurisdictionList('CH, DE, IT-25')).toEqual([
      { country: 'CH' },
      { country: 'DE' },
      { country: 'IT', subdivision: 'IT-25' },
    ]);
  });

  it('parses array input', () => {
    expect(parseJurisdictionList(['CH-ZH', 'AT'])).toEqual([
      { country: 'CH', subdivision: 'CH-ZH' },
      { country: 'AT' },
    ]);
  });

  it('drops invalid tokens silently', () => {
    expect(parseJurisdictionList('CH, garbage, DE-BY, ZZ-ZZ-ZZ')).toEqual([
      { country: 'CH' },
      { country: 'DE', subdivision: 'DE-BY' },
    ]);
  });
});
