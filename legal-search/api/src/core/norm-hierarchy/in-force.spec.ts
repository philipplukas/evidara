import { describe, expect, it } from 'vitest';
import { inForceExclusionClauses, resolveInForceState } from './in-force';

describe('resolveInForceState', () => {
  it('reports a repealed norm as not in force at a later date', () => {
    // The point of the whole temporal-validity field: a norm repealed in 2018
    // cannot be used to judge a ban enacted in 2019.
    const norm = { in_force_from: '2005-01-01', in_force_until: '2018-12-31' };
    expect(resolveInForceState(norm, '2019-06-01')).toBe('repealed');
  });

  it('reports the same norm as in force at a date inside its window', () => {
    const norm = { in_force_from: '2005-01-01', in_force_until: '2018-12-31' };
    expect(resolveInForceState(norm, '2010-06-01')).toBe('in_force');
  });

  it('treats `in_force_until` as the last day the norm WAS in force', () => {
    const norm = { in_force_from: '2005-01-01', in_force_until: '2018-12-31' };
    expect(resolveInForceState(norm, '2018-12-31')).toBe('in_force');
    expect(resolveInForceState(norm, '2019-01-01')).toBe('repealed');
  });

  it('reports a norm as not yet in force before its start date', () => {
    expect(resolveInForceState({ in_force_from: '2020-01-01' }, '2019-06-01')).toBe(
      'not_yet_in_force',
    );
  });

  it('keeps an open-ended norm in force', () => {
    expect(resolveInForceState({ in_force_from: '2005-01-01' }, '2026-07-14')).toBe('in_force');
  });

  it('says `unknown` — not `in_force` — when a norm is marked repealed without a date', () => {
    // Guessing `in_force` here is the confident fabrication ADR-0033 exists to
    // prevent; guessing `repealed` would hide law that may well have applied.
    const norm = { in_force_from: '2005-01-01', lifecycle_status: 'repealed' };
    expect(resolveInForceState(norm, '2019-06-01')).toBe('unknown');
  });

  it('says `unknown` when no start date is held at all', () => {
    expect(resolveInForceState({}, '2019-06-01')).toBe('unknown');
  });

  it('settles the question from the repeal date even without a start date', () => {
    expect(resolveInForceState({ in_force_until: '2018-12-31' }, '2019-06-01')).toBe('repealed');
  });
});

describe('inForceExclusionClauses', () => {
  it('excludes only norms KNOWN to be outside force, so unknown-dated norms survive', () => {
    // Both clauses are `must_not` ranges; a document missing the field does not
    // match a range, so it is kept and reported as `unknown` rather than
    // silently dropped from the corpus the agent can see.
    expect(inForceExclusionClauses('2019-06-01')).toEqual([
      { range: { in_force_until: { lt: '2019-06-01' } } },
      { range: { in_force_from: { gt: '2019-06-01' } } },
    ]);
  });
});
