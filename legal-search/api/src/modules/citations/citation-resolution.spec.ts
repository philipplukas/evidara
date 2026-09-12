import { describe, expect, it } from 'vitest';
import { resolveAgainstTargets } from './citation-resolution';
import type { CitationTarget } from './citations.repository';

function target(overrides: Partial<CitationTarget> = {}): CitationTarget {
  return {
    document_id: 'doc_bv',
    identifier_type: 'abbrev_art',
    identifier_value: 'BV/36',
    title: 'Bundesverfassung',
    document_type: 'law',
    ...overrides,
  };
}

describe('resolveAgainstTargets', () => {
  // ── The POSITIVE case. Without it, a resolver that resolves NOTHING passes
  // every "no wrong edges" assertion in this file.
  it('resolves a key that exactly one document answers', () => {
    const bv = target();
    const resolution = resolveAgainstTargets('abbrev_art:BV/36', [bv]);

    expect(resolution.status).toBe('resolved');
    if (resolution.status !== 'resolved') throw new Error('unreachable');
    expect(resolution.target.document_id).toBe('doc_bv');
    expect(resolution.reason).toBeNull();
  });

  it('prefers the provision-level row when one document publishes several', () => {
    // Statute row and article row, SAME document — not ambiguity. The article
    // row is the answer, because "Art. 36 BV" addresses the article (#573).
    const statuteRow = target({ section_id: undefined });
    const articleRow = target({ section_id: 'sec_36', section_anchor: 'art_36' });

    const resolution = resolveAgainstTargets('abbrev_art:BV/36', [statuteRow, articleRow]);

    expect(resolution.status).toBe('resolved');
    if (resolution.status !== 'resolved') throw new Error('unreachable');
    expect(resolution.target.section_id).toBe('sec_36');
  });

  // ── The three unresolved states, each distinguishable from the others.
  it('reports a key-less citation as not_normalizable', () => {
    const resolution = resolveAgainstTargets(undefined, []);
    expect(resolution).toMatchObject({ status: 'unresolved', reason: 'not_normalizable' });
  });

  it('reports a well-formed key with no matching norm as no_target_in_corpus', () => {
    const resolution = resolveAgainstTargets('sr:210', []);
    expect(resolution).toMatchObject({ status: 'unresolved', reason: 'no_target_in_corpus' });
  });

  // ── THE REFUSAL. A wrong edge asserts a relationship between two laws that
  // does not exist; two different documents answering one key is a real state
  // and not a free choice.
  it('refuses a key that several DIFFERENT documents answer', () => {
    const resolution = resolveAgainstTargets('abbrev_art:EG/1', [
      target({ document_id: 'doc_zh_eg', title: 'Einführungsgesetz ZH' }),
      target({ document_id: 'doc_be_eg', title: 'Einführungsgesetz BE' }),
    ]);

    expect(resolution).toMatchObject({ status: 'unresolved', reason: 'ambiguous' });
    // The rivals come back UNRANKED so the caller can disambiguate on evidence
    // this function does not have.
    expect(resolution.candidates.map((c) => c.document_id)).toEqual(['doc_zh_eg', 'doc_be_eg']);
    // And emphatically no target: a narrowed key is not a resolved one.
    expect(resolution.target).toBeNull();
  });
});
