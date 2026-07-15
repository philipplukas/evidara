/**
 * These tests run against the REAL generated vocabulary
 * (`contracts/vocabularies/jurisdiction-hierarchy.json`), not a fixture. The
 * whole claim of ADR-0033 is that the hierarchy is a fact about the seeded
 * jurisdictions — mocking the tree would test the walk while assuming away the
 * thing that can actually be wrong.
 *
 * `jur_ch_gemeinde_261` is the City of Zurich: the exact place the dog question
 * is asked about.
 */
import { describe, expect, it } from 'vitest';
import {
  deriveDocumentLevel,
  deriveSubordinateTo,
  getGoverningScopes,
  getJurisdiction,
  getNormHierarchyLevels,
  normLevelRank,
} from './norm-hierarchy.vocabulary';

const ZURICH_CITY = 'jur_ch_gemeinde_261';
const ZURICH_CANTON = 'jur_ch_zh';
const CH_FEDERAL = 'jur_ch_federal';
const CH = 'jur_ch';

describe('jurisdiction levels', () => {
  it('sources the level from the jurisdiction, not the text', () => {
    expect(getJurisdiction(ZURICH_CITY)?.level).toBe('municipal');
    expect(getJurisdiction(ZURICH_CANTON)?.level).toBe('cantonal');
    expect(getJurisdiction(CH_FEDERAL)?.level).toBe('federal');
    expect(getJurisdiction('jur_eu')?.level).toBe('international');
  });

  it('ranks the hierarchy of norms so that federal outranks cantonal outranks municipal', () => {
    expect(normLevelRank('constitutional')).toBeLessThan(normLevelRank('federal'));
    expect(normLevelRank('federal')).toBeLessThan(normLevelRank('cantonal'));
    expect(normLevelRank('cantonal')).toBeLessThan(normLevelRank('municipal'));
  });
});

describe('deriveDocumentLevel', () => {
  it('gives a document the level of its jurisdiction', () => {
    expect(deriveDocumentLevel([ZURICH_CITY])).toBe('municipal');
    expect(deriveDocumentLevel([ZURICH_CANTON])).toBe('cantonal');
    expect(deriveDocumentLevel([CH_FEDERAL])).toBe('federal');
  });

  it('takes the most specific jurisdiction when a document carries several', () => {
    // Cantonal law scoped to Switzerland is cantonal law, not federal law.
    expect(deriveDocumentLevel([CH, ZURICH_CANTON])).toBe('cantonal');
  });

  it('lets a document declare `constitutional` — the one level the jurisdiction cannot supply', () => {
    // The BV is enacted by jur_ch_federal exactly like the TSchG, so no
    // jurisdiction lookup can tell them apart.
    expect(deriveDocumentLevel([CH_FEDERAL], 'constitutional')).toBe('constitutional');
  });

  it('refuses a declared level that would demote the norm below its jurisdiction', () => {
    // A mislabelled upstream row must not turn federal law into municipal law.
    expect(deriveDocumentLevel([CH_FEDERAL], 'municipal')).toBe('federal');
  });

  it('returns undefined for a jurisdiction the hierarchy does not know', () => {
    expect(deriveDocumentLevel(['jur_atlantis'])).toBeUndefined();
  });
});

describe('getGoverningScopes', () => {
  it('reaches federal law from a canton, though federal is not an ancestor', () => {
    // jur_ch_federal is a SIBLING of the cantons under jur_ch. A parent-only
    // walk would never find it — and preemption would be unanswerable.
    const scopes = getGoverningScopes(ZURICH_CANTON).map((s) => s.jurisdiction_id);
    expect(scopes).toContain(CH_FEDERAL);
    expect(scopes).toContain(ZURICH_CANTON);
  });

  it('does not pull in sibling cantons', () => {
    const scopes = getGoverningScopes(ZURICH_CITY).map((s) => s.jurisdiction_id);
    expect(scopes).not.toContain('jur_ch_be');
  });

  it('orders scopes most authoritative first', () => {
    const scopes = getGoverningScopes(ZURICH_CITY);
    const ranks = scopes.map((s) => normLevelRank(s.level));
    expect(ranks).toEqual([...ranks].sort((a, b) => a - b));
  });

  it('returns nothing for an unknown place — absence, not "nothing governs it"', () => {
    expect(getGoverningScopes('jur_atlantis')).toEqual([]);
  });
});

describe('deriveSubordinateTo', () => {
  it('makes a Zurich communal ordinance subordinate to Zurich cantonal law and to federal law', () => {
    const superiors = deriveSubordinateTo([ZURICH_CITY]);
    expect(superiors).toContain(ZURICH_CANTON);
    expect(superiors).toContain(CH_FEDERAL);
    expect(superiors).toContain(CH);
    expect(superiors).not.toContain(ZURICH_CITY);
  });

  it('makes cantonal law subordinate to federal law and nothing below it', () => {
    expect(deriveSubordinateTo([ZURICH_CANTON])).toEqual([CH, CH_FEDERAL]);
  });

  it('leaves federal law subordinate to no canton or commune', () => {
    expect(deriveSubordinateTo([CH_FEDERAL])).not.toContain(ZURICH_CANTON);
  });
});

describe('getNormHierarchyLevels', () => {
  it('returns the four Swiss layers for a commune, most authoritative first', () => {
    const levels = getNormHierarchyLevels(ZURICH_CITY);
    expect(levels.map((l) => l.level)).toEqual([
      'constitutional',
      'federal',
      'cantonal',
      'municipal',
    ]);
  });

  it('resolves the constitutional level to the federal jurisdictions that enact it', () => {
    const levels = getNormHierarchyLevels(ZURICH_CITY);
    const constitutional = levels.find((l) => l.level === 'constitutional');
    expect(constitutional?.jurisdictionIds).toContain(CH_FEDERAL);
  });

  it('names the canton and the federation for the City of Zurich', () => {
    const levels = getNormHierarchyLevels(ZURICH_CITY);
    expect(levels.find((l) => l.level === 'cantonal')?.jurisdictionIds).toEqual([ZURICH_CANTON]);
    expect(levels.find((l) => l.level === 'federal')?.jurisdictionIds).toContain(CH_FEDERAL);
    expect(levels.find((l) => l.level === 'municipal')?.jurisdictionIds).toEqual([ZURICH_CITY]);
  });

  it('stops at federal for a federal jurisdiction — no cantonal or municipal layer', () => {
    const levels = getNormHierarchyLevels(CH_FEDERAL).map((l) => l.level);
    expect(levels).not.toContain('cantonal');
    expect(levels).not.toContain('municipal');
  });
});
