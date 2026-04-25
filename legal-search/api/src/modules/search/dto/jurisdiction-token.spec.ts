/**
 * Jurisdiction-token parser tests.
 *
 * WHY THIS TEST EXISTS:
 * The OpenAPI contract (T5.2 / v0.4.0) accepts country codes (`CH`),
 * subdivision codes (`CH-ZH`), and canonical platform-control IDs
 * (`jur_ch_federal`, `jur_ch_gemeinde_261`, `jur_de_05315000`) in the
 * `jurisdiction` query param. A typo like `ch-zh` (lowercased) or `chzh`
 * (no delimiter) must not silently slip through as a valid ISO token —
 * the parser owns that gate. Likewise a stray `jur_` prefix on garbage
 * (`jur_!!!`) must not be accepted as a canonical ID.
 */

import { describe, expect, it } from 'vitest';
import {
  parseJurisdictionList,
  parseJurisdictionToken,
  partitionJurisdictionTokens,
} from './jurisdiction-token';

describe('parseJurisdictionToken', () => {
  it('classifies a plain country code as iso-country', () => {
    expect(parseJurisdictionToken('CH')).toEqual({
      kind: 'iso-country',
      country: 'CH',
    });
  });

  it('classifies a subdivision code as iso-subdivision and preserves the full ISO 3166-2 form', () => {
    expect(parseJurisdictionToken('CH-ZH')).toEqual({
      kind: 'iso-subdivision',
      country: 'CH',
      subdivision: 'CH-ZH',
    });
  });

  it('normalizes lowercased ISO input to uppercase', () => {
    expect(parseJurisdictionToken('ch-zh')).toEqual({
      kind: 'iso-subdivision',
      country: 'CH',
      subdivision: 'CH-ZH',
    });
    expect(parseJurisdictionToken('de')).toEqual({
      kind: 'iso-country',
      country: 'DE',
    });
  });

  it('trims surrounding whitespace', () => {
    expect(parseJurisdictionToken('  IT-25  ')).toEqual({
      kind: 'iso-subdivision',
      country: 'IT',
      subdivision: 'IT-25',
    });
  });

  it('handles numeric-suffix subdivisions (IT regioni, AT Bundesländer)', () => {
    expect(parseJurisdictionToken('IT-25')?.subdivision).toBe('IT-25');
    expect(parseJurisdictionToken('AT-9')?.subdivision).toBe('AT-9');
  });

  it('classifies canonical federal IDs as canonical', () => {
    expect(parseJurisdictionToken('jur_ch_federal')).toEqual({
      kind: 'canonical',
      canonicalId: 'jur_ch_federal',
    });
  });

  it('classifies canonical canton IDs as canonical', () => {
    expect(parseJurisdictionToken('jur_ch_zh')).toEqual({
      kind: 'canonical',
      canonicalId: 'jur_ch_zh',
    });
  });

  it('classifies canonical gemeinde IDs (CH municipality) as canonical', () => {
    expect(parseJurisdictionToken('jur_ch_gemeinde_261')).toEqual({
      kind: 'canonical',
      canonicalId: 'jur_ch_gemeinde_261',
    });
  });

  it('classifies canonical DE pilot IDs (8-digit AGS) as canonical', () => {
    expect(parseJurisdictionToken('jur_de_05315000')).toEqual({
      kind: 'canonical',
      canonicalId: 'jur_de_05315000',
    });
  });

  it('lowercases mixed-case canonical IDs before matching', () => {
    expect(parseJurisdictionToken('JUR_CH_FEDERAL')).toEqual({
      kind: 'canonical',
      canonicalId: 'jur_ch_federal',
    });
  });

  it('rejects malformed ISO tokens', () => {
    expect(parseJurisdictionToken('')).toBeNull();
    expect(parseJurisdictionToken('CHH')).toBeNull();
    expect(parseJurisdictionToken('CH-')).toBeNull();
    expect(parseJurisdictionToken('CHZH')).toBeNull();
    expect(parseJurisdictionToken('CH-ZH-XX')).toBeNull();
    expect(parseJurisdictionToken('CH ZH')).toBeNull();
    expect(parseJurisdictionToken('C1')).toBeNull();
  });

  it('rejects malformed canonical tokens', () => {
    expect(parseJurisdictionToken('jur_')).toBeNull();
    expect(parseJurisdictionToken('jur_!!!')).toBeNull();
    expect(parseJurisdictionToken('jur ch federal')).toBeNull();
    expect(parseJurisdictionToken('not_jur_ch')).toBeNull();
  });

  it('rejects garbage input that resembles neither shape', () => {
    expect(parseJurisdictionToken('garbage')).toBeNull();
    expect(parseJurisdictionToken('123')).toBeNull();
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

  it('parses comma-separated strings of mixed shapes', () => {
    expect(parseJurisdictionList('CH, DE, IT-25, jur_ch_federal')).toEqual([
      { kind: 'iso-country', country: 'CH' },
      { kind: 'iso-country', country: 'DE' },
      { kind: 'iso-subdivision', country: 'IT', subdivision: 'IT-25' },
      { kind: 'canonical', canonicalId: 'jur_ch_federal' },
    ]);
  });

  it('parses array input', () => {
    expect(parseJurisdictionList(['CH-ZH', 'AT', 'jur_ch_gemeinde_261'])).toEqual([
      { kind: 'iso-subdivision', country: 'CH', subdivision: 'CH-ZH' },
      { kind: 'iso-country', country: 'AT' },
      { kind: 'canonical', canonicalId: 'jur_ch_gemeinde_261' },
    ]);
  });

  it('drops invalid tokens silently', () => {
    expect(parseJurisdictionList('CH, garbage, DE-BY, ZZ-ZZ-ZZ, jur_!!!')).toEqual([
      { kind: 'iso-country', country: 'CH' },
      { kind: 'iso-subdivision', country: 'DE', subdivision: 'DE-BY' },
    ]);
  });
});

describe('partitionJurisdictionTokens', () => {
  it('splits a mixed list into iso and canonical buckets', () => {
    const parsed = parseJurisdictionList(['CH-ZH', 'jur_ch_gemeinde_261', 'DE']);
    expect(partitionJurisdictionTokens(parsed)).toEqual({
      isoTokens: ['ch-zh', 'de'],
      canonicalIds: ['jur_ch_gemeinde_261'],
    });
  });

  it('returns empty buckets for an empty input', () => {
    expect(partitionJurisdictionTokens([])).toEqual({
      isoTokens: [],
      canonicalIds: [],
    });
  });

  it('routes pure-canonical lists to canonicalIds only', () => {
    const parsed = parseJurisdictionList(['jur_ch_federal', 'jur_de_05315000']);
    expect(partitionJurisdictionTokens(parsed)).toEqual({
      isoTokens: [],
      canonicalIds: ['jur_ch_federal', 'jur_de_05315000'],
    });
  });

  it('routes pure-iso lists to isoTokens only (lowercased to match index)', () => {
    const parsed = parseJurisdictionList(['CH', 'DE-BY']);
    expect(partitionJurisdictionTokens(parsed)).toEqual({
      isoTokens: ['ch', 'de-by'],
      canonicalIds: [],
    });
  });
});
