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

  it('agrees with the producers on ONE boundary date, deliberately (#843)', () => {
    // The consumer half of a two-sided pin. The producer half is
    // `platform-control/tests/unit/test_lexfind_api_provider.py`
    // ::test_the_exclusive_upstream_end_date_is_converted_to_the_inclusive_boundary,
    // which starts from a real LexFind record — ZH 415.611, measured 2026-09-03,
    // `version_inactive_since: "01.07.2026"` — and emits `in_force_until:
    // 2026-06-30`. THIS test consumes that exact value.
    //
    // Read the two together: the act was repealed with effect from 1 July 2026,
    // so 30 June is the last day it applied and 1 July is the first day it did
    // not. If either side ever drifts by a day, one of these two tests fails and
    // names the other. Before #843 they were the same date in two files on
    // opposite sides of the boundary, agreeing by coincidence.
    const zh415611 = { in_force_from: '2017-02-01', in_force_until: '2026-06-30' };
    expect(resolveInForceState(zh415611, '2026-06-30')).toBe('in_force');
    expect(resolveInForceState(zh415611, '2026-07-01')).toBe('repealed');
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

  it('uses `lt`, not `lte`, so the last day in force is not filtered out (#843)', () => {
    // The index filter has to encode the SAME inclusive boundary as
    // `resolveInForceState`, or a norm reads `in_force` on its last day in the
    // detail view while the search that should surface it has already dropped it.
    // `lt` keeps a document whose `in_force_until` equals the as-of date; `lte`
    // would exclude it. Asserted on the date itself, not on the shape.
    const [untilClause] = inForceExclusionClauses('2026-06-30') as [
      { range: { in_force_until: Record<string, string> } },
    ];
    expect(untilClause.range.in_force_until).toEqual({ lt: '2026-06-30' });
    expect(untilClause.range.in_force_until.lte).toBeUndefined();
  });
});
