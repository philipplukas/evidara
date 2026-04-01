import { describe, expect, it } from 'vitest';
import type { ContextAggregations } from '../entities/search.entities';
import { mapContextAggregations } from './search-context.mapper';

// ─── Fixtures ───

const fullContext: ContextAggregations = {
  jurisdictions: [
    { key: 'CH', doc_count: 500 },
    { key: 'AT', doc_count: 200 },
  ],
  languages: [
    { key: 'de', doc_count: 600 },
    { key: 'fr', doc_count: 100 },
    { key: 'it', doc_count: 50 },
  ],
  source_types: [
    { key: 'law', doc_count: 300 },
    { key: 'decision', doc_count: 400 },
  ],
};

const emptyContext: ContextAggregations = {
  jurisdictions: [],
  languages: [],
  source_types: [],
};

// ─── Basic Shape ───

describe('mapContextAggregations', () => {
  it('should return all context arrays', () => {
    const ctx = mapContextAggregations(fullContext);
    expect(ctx).toHaveProperty('jurisdictions');
    expect(ctx).toHaveProperty('languages');
    expect(ctx).toHaveProperty('sourceTypes');
    expect(ctx).toHaveProperty('exactMatches');
  });

  it('should return empty arrays for empty aggregations', () => {
    const ctx = mapContextAggregations(emptyContext);
    expect(ctx.jurisdictions).toEqual([]);
    expect(ctx.languages).toEqual([]);
    expect(ctx.sourceTypes).toEqual([{ key: 'all', label: 'All', active: true }]);
    expect(ctx.exactMatches).toEqual([]);
  });
});

// ─── Jurisdictions ───

describe('jurisdiction chips', () => {
  it('should produce chips with human-readable labels', () => {
    const ctx = mapContextAggregations(fullContext);
    const labels = ctx.jurisdictions.map((j) => j.label);
    expect(labels).toContain('Switzerland');
    expect(labels).toContain('Austria');
  });

  it('should include iconKey for known jurisdictions', () => {
    const ctx = mapContextAggregations(fullContext);
    const ch = ctx.jurisdictions.find((j) => j.label === 'Switzerland');
    expect(ch?.iconKey).toBe('ch');
  });

  it('should default all jurisdictions to active', () => {
    const ctx = mapContextAggregations(fullContext);
    for (const j of ctx.jurisdictions) {
      expect(j.active).toBe(true);
    }
  });

  it('should lowercase the key', () => {
    const ctx = mapContextAggregations(fullContext);
    const ch = ctx.jurisdictions.find((j) => j.label === 'Switzerland');
    expect(ch?.key).toBe('ch');
  });

  it('should fall back to raw key for unknown jurisdictions', () => {
    const ctx = mapContextAggregations({
      ...fullContext,
      jurisdictions: [{ key: 'XX', doc_count: 5 }],
    });
    expect(ctx.jurisdictions[0].label).toBe('XX');
    expect(ctx.jurisdictions[0].iconKey).toBeUndefined();
  });
});

// ─── Languages ───

describe('language chips', () => {
  it('should produce uppercase labels', () => {
    const ctx = mapContextAggregations(fullContext);
    const labels = ctx.languages.map((l) => l.label);
    expect(labels).toContain('DE');
    expect(labels).toContain('FR');
    expect(labels).toContain('IT');
  });

  it('should default only DE to active', () => {
    const ctx = mapContextAggregations(fullContext);
    const de = ctx.languages.find((l) => l.key === 'de');
    const fr = ctx.languages.find((l) => l.key === 'fr');
    expect(de?.active).toBe(true);
    expect(fr?.active).toBe(false);
  });

  it('should fall back to uppercase key for unknown languages', () => {
    const ctx = mapContextAggregations({
      ...fullContext,
      languages: [{ key: 'rm', doc_count: 10 }],
    });
    expect(ctx.languages[0].label).toBe('RM');
    expect(ctx.languages[0].active).toBe(false);
  });
});

// ─── Source Types ───

describe('source type chips', () => {
  it('should prepend "All" option as active', () => {
    const ctx = mapContextAggregations(fullContext);
    expect(ctx.sourceTypes[0]).toEqual({
      key: 'all',
      label: 'All',
      active: true,
    });
  });

  it('should apply human-readable labels for known types', () => {
    const ctx = mapContextAggregations(fullContext);
    const labels = ctx.sourceTypes.map((s) => s.label);
    expect(labels).toContain('Law');
    expect(labels).toContain('Court decision');
  });

  it('should mark all non-"All" source types as inactive', () => {
    const ctx = mapContextAggregations(fullContext);
    for (const s of ctx.sourceTypes.slice(1)) {
      expect(s.active).toBe(false);
    }
  });

  it('should fall back to raw key for unknown source types', () => {
    const ctx = mapContextAggregations({
      ...fullContext,
      source_types: [{ key: 'regulation', doc_count: 5 }],
    });
    expect(ctx.sourceTypes[1].label).toBe('regulation');
  });
});
