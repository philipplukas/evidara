import { describe, expect, it, vi } from 'vitest';
import type { WarnFn } from '../../../core/types/warn';
import type { SearchHitEntity } from '../entities/search.entities';
import {
  composeActions,
  composeBadges,
  composeLanguage,
  composeMetadata,
  composeRelatedCounts,
  composeSubtitle,
  mapSearchHitToView,
} from './search-result.mapper';

// ─── Fixtures ───

const lawHit: SearchHitEntity = {
  document_id: 'doc_001',
  title: 'Obligationenrecht',
  snippet: 'Art. 1 OR — Vertragsschluss',
  jurisdiction: 'CH',
  document_type: 'law',
  effective_date: '2024-01-01',
  structural_path: 'OR › Gesellschaftsrecht › Verantwortlichkeit',
  language: 'de',
  sections_count: 42,
  citations_count: 15,
  related_commentary_count: 8,
  related_decisions_count: 23,
};

const decisionHit: SearchHitEntity = {
  document_id: 'doc_002',
  title: 'BGE 144 III 264',
  jurisdiction: 'CH',
  document_type: 'decision',
  effective_date: '2018-06-15',
};

const minimalHit: SearchHitEntity = {
  document_id: 'doc_003',
  title: 'Unknown Document',
};

// ─── composeBadges ───

describe('composeBadges', () => {
  it('should produce a badge with correct label and color for known type', () => {
    const badges = composeBadges(lawHit);
    expect(badges).toHaveLength(1);
    expect(badges[0].label).toBe('Gesetz');
    expect(badges[0].colorKey).toBe('blue');
  });

  it('should include iconKey for known jurisdiction', () => {
    const badges = composeBadges(lawHit);
    expect(badges[0].iconKey).toBe('ch');
  });

  it('should fall back to generic badge for unknown type', () => {
    const hit = { ...minimalHit, document_type: 'regulation' };
    const badges = composeBadges(hit);
    expect(badges[0].label).toBe('Dokument');
    expect(badges[0].colorKey).toBe('slate');
  });

  it('should warn on unknown document_type', () => {
    const warn: WarnFn = vi.fn();
    const hit = { ...minimalHit, document_type: 'regulation' };
    composeBadges(hit, 'de', warn);
    expect(warn).toHaveBeenCalledWith('unknown_document_type', {
      document_id: 'doc_003',
      document_type: 'regulation',
    });
  });

  it('should warn on unknown jurisdiction', () => {
    const warn: WarnFn = vi.fn();
    const hit = { ...minimalHit, jurisdiction: 'XX' };
    composeBadges(hit, 'de', warn);
    expect(warn).toHaveBeenCalledWith('unknown_jurisdiction', {
      document_id: 'doc_003',
      jurisdiction: 'XX',
    });
  });

  it('should not warn for missing document_type (empty string)', () => {
    const warn: WarnFn = vi.fn();
    composeBadges(minimalHit, 'de', warn);
    expect(warn).not.toHaveBeenCalled();
  });
});

// ─── composeSubtitle ───

describe('composeSubtitle', () => {
  it('should compose "Schweiz · Gesetz" for CH + law', () => {
    expect(composeSubtitle(lawHit)).toBe('Schweiz · Gesetz');
  });

  it('should compose "Schweiz · Gerichtsentscheid" for CH + decision', () => {
    expect(composeSubtitle(decisionHit)).toBe('Schweiz · Gerichtsentscheid');
  });

  it('should fall back to document_type label for unknown jurisdiction', () => {
    const hit = { ...minimalHit, document_type: 'law' };
    expect(composeSubtitle(hit)).toBe('Gesetz');
  });

  it('should fall back to "Dokument" for fully unknown hit', () => {
    expect(composeSubtitle(minimalHit)).toBe('Dokument');
  });
});

// ─── composeMetadata ───

describe('composeMetadata', () => {
  it('should produce "In Kraft" row for law with effective_date', () => {
    const rows = composeMetadata(lawHit);
    expect(rows).toContainEqual({
      label: 'In Kraft',
      value: '2024-01-01',
    });
  });

  it('should produce "Datum" row for decision', () => {
    const rows = composeMetadata(decisionHit);
    expect(rows).toContainEqual({
      label: 'Datum',
      value: '2018-06-15',
    });
  });

  it('should return empty array for missing date', () => {
    expect(composeMetadata(minimalHit)).toEqual([]);
  });
});

// ─── composeRelatedCounts ───

describe('composeRelatedCounts', () => {
  it('should produce counts for law hit', () => {
    const counts = composeRelatedCounts(lawHit);
    expect(counts).toHaveLength(3);
    expect(counts.find((c) => c.label === 'Kommentare')?.count).toBe(8);
    expect(counts.find((c) => c.label === 'Gerichtsentscheide')?.count).toBe(23);
    expect(counts.find((c) => c.label === 'Zitationen')?.count).toBe(15);
  });

  it('should return empty array when no counts', () => {
    expect(composeRelatedCounts(minimalHit)).toEqual([]);
  });

  it('should skip zero counts', () => {
    const hit = { ...minimalHit, related_commentary_count: 0, citations_count: 0 };
    expect(composeRelatedCounts(hit)).toEqual([]);
  });
});

// ─── composeActions ───

describe('composeActions', () => {
  it('should produce law-specific actions for law type', () => {
    const actions = composeActions(lawHit);
    expect(actions).toHaveLength(2);
    expect(actions[0].label).toBe('Artikel \u00f6ffnen');
  });

  it('should produce generic action for unknown type', () => {
    const hit = { ...minimalHit, document_type: 'regulation' };
    const actions = composeActions(hit);
    expect(actions).toHaveLength(1);
    expect(actions[0].label).toBe('\u00d6ffnen');
  });

  it('should warn on unknown document_type', () => {
    const warn: WarnFn = vi.fn();
    const hit = { ...minimalHit, document_type: 'regulation' };
    composeActions(hit, 'de', warn);
    expect(warn).toHaveBeenCalledWith('unknown_document_type_actions', {
      document_id: 'doc_003',
      document_type: 'regulation',
    });
  });
});

// ─── composeLanguage ───

describe('composeLanguage', () => {
  it('should produce language view for known language', () => {
    const lang = composeLanguage({ language: 'de' });
    expect(lang).toEqual({
      display: 'de',
      original: 'de',
      isTranslation: false,
    });
  });

  it('should return undefined for missing language', () => {
    expect(composeLanguage({})).toBeUndefined();
  });
});

// ─── mapSearchHitToView ───

describe('mapSearchHitToView', () => {
  it('should produce a complete view for a law hit', () => {
    const view = mapSearchHitToView(lawHit);
    expect(view.id).toBe('doc_001');
    expect(view.type).toBe('law');
    expect(view.title).toBe('Obligationenrecht');
    expect(view.snippet).toBe('Art. 1 OR — Vertragsschluss');
    expect(view.structuralContext).toBe('OR › Gesellschaftsrecht › Verantwortlichkeit');
    expect(view.badges).toHaveLength(1);
    expect(view.metadataRows).toHaveLength(1);
    expect(view.relatedCounts).toHaveLength(3);
    expect(view.actions).toHaveLength(2);
    expect(view.contentLanguage?.display).toBe('de');
  });

  it('should omit structuralContext when missing', () => {
    const view = mapSearchHitToView(decisionHit);
    expect(view.structuralContext).toBeUndefined();
  });

  it('should default snippet to empty string', () => {
    const view = mapSearchHitToView(minimalHit);
    expect(view.snippet).toBe('');
  });

  it('should always return arrays, never undefined', () => {
    const view = mapSearchHitToView(minimalHit);
    expect(Array.isArray(view.badges)).toBe(true);
    expect(Array.isArray(view.metadataRows)).toBe(true);
    expect(Array.isArray(view.relatedCounts)).toBe(true);
    expect(Array.isArray(view.actions)).toBe(true);
  });

  it('should thread WarnFn through composition', () => {
    const warn: WarnFn = vi.fn();
    const hit = {
      ...minimalHit,
      document_type: 'regulation',
      jurisdiction: 'XX',
    };
    mapSearchHitToView(hit, 'de', warn);
    // Should have warned about unknown type and jurisdiction
    expect(warn).toHaveBeenCalled();
    const calls = (warn as ReturnType<typeof vi.fn>).mock.calls;
    const events = calls.map((c) => c[0]);
    expect(events).toContain('unknown_document_type');
    expect(events).toContain('unknown_jurisdiction');
  });
});

// ─── Locale Switching (ADR-0013) ───

describe('locale-aware label resolution', () => {
  it('should render French badges when locale is fr', () => {
    const badges = composeBadges(lawHit, 'fr');
    expect(badges[0].label).toBe('Loi');
  });

  it('should render French subtitle when locale is fr', () => {
    expect(composeSubtitle(lawHit, 'fr')).toBe('Suisse · Loi');
  });

  it('should render French metadata when locale is fr', () => {
    const rows = composeMetadata(lawHit, 'fr');
    expect(rows[0].label).toBe('En vigueur');
  });

  it('should render French related counts when locale is fr', () => {
    const counts = composeRelatedCounts(
      { ...lawHit, related_commentary_count: 3 },
      'fr',
    );
    expect(counts[0].label).toBe('Commentaires');
  });

  it('should render French actions when locale is fr', () => {
    const actions = composeActions(lawHit, 'fr');
    expect(actions[0].label).toBe("Ouvrir l'article");
  });

  it('should compose complete French view', () => {
    const view = mapSearchHitToView(lawHit, 'fr');
    expect(view.badges[0].label).toBe('Loi');
    expect(view.subtitle).toBe('Suisse · Loi');
    expect(view.actions[0].label).toBe("Ouvrir l'article");
  });
});
