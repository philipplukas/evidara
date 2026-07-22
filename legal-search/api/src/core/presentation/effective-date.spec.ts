import { describe, expect, it } from 'vitest';
import { effectiveDateLabel, isEffectiveDateUnverified } from './effective-date';

describe('isEffectiveDateUnverified', () => {
  it('flags decisions, whose effective_date is scraped from the body (#759)', () => {
    expect(isEffectiveDateUnverified('decision')).toBe(true);
  });

  it('does not flag laws, which carry an in-force date from a different path', () => {
    expect(isEffectiveDateUnverified('law')).toBe(false);
    expect(isEffectiveDateUnverified(undefined)).toBe(false);
  });
});

describe('effectiveDateLabel', () => {
  it('qualifies a decision date so it does not read as verified', () => {
    expect(effectiveDateLabel('decision', 'de')).toBe('Datum (unbestätigt)');
    expect(effectiveDateLabel('decision', 'fr')).toBe('Date (non vérifiée)');
  });

  it('never emits a bare date label, which is what gave the guess its authority', () => {
    expect(effectiveDateLabel('decision', 'de')).not.toBe('Datum');
    expect(effectiveDateLabel('decision', 'fr')).not.toBe('Date');
  });

  it('leaves the in-force label alone for everything else', () => {
    expect(effectiveDateLabel('law', 'de')).toBe('In Kraft');
    expect(effectiveDateLabel('law', 'fr')).toBe('En vigueur');
    expect(effectiveDateLabel(undefined, 'de')).toBe('In Kraft');
  });
});
