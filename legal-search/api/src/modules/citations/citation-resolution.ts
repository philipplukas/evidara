/**
 * THE citation-resolution rule — one implementation, one place.
 *
 * Given a citation's canonical key (`sr:210`, `abbrev_art:BV/36`) and the
 * `citation-targets` rows that key addresses, decide whether an EDGE exists.
 *
 * Why this file exists at all: the rule was written twice and the two copies
 * disagreed, with the weaker one on the write path.
 *
 *   `CitationsService.resolve` (read path) REFUSED a key naming several
 *   documents and returned `unresolved_reason: 'ambiguous'` with the
 *   candidates.
 *
 *   `ProjectionsService.resolveCitations` (write path) built a
 *   `Map<key, match>` from the search hits and let the LAST hit win
 *   (`projections/opensearch.adapter.ts`, `resolveCitationTargets`). An
 *   ambiguous key was therefore persisted onto the citation row as
 *   `resolved: true` plus one arbitrarily-chosen `target_document_id` — a
 *   guess wearing a resolved flag, written into the index, and thereafter
 *   indistinguishable from a real edge.
 *
 * A wrong edge asserts a relationship between two laws that does not exist,
 * which ADR-0033 treats as strictly worse than a missing one. So the refusal
 * is the rule, and both callers now get it from here.
 *
 * The three unresolved states are distinct on purpose (ADR-0052, #958):
 *
 *   `not_normalizable`    — extractor gap. The string names no identifier we
 *                           can key on, so resolution was never attempted.
 *   `no_target_in_corpus` — coverage gap. The key is well-formed; the norm it
 *                           names is simply not ingested.
 *   `ambiguous`           — several DIFFERENT documents are addressable by
 *                           this key. Not an error, and not a free choice.
 *
 * Collapsing them into a bare `resolved: false` is how a graph acquires
 * silently missing edges that nobody can attribute.
 */

import type { CitationTarget } from './citations.repository';

export type CitationUnresolvedReason = 'not_normalizable' | 'no_target_in_corpus' | 'ambiguous';

export type CitationResolution =
  | {
      status: 'resolved';
      reason: null;
      /** The single document the key addresses. */
      target: CitationTarget;
      /** Every row for the key — one document may publish several. */
      candidates: CitationTarget[];
    }
  | {
      status: 'unresolved';
      reason: CitationUnresolvedReason;
      target: null;
      /** On `ambiguous`, the rival norms — UNRANKED. Empty otherwise. */
      candidates: CitationTarget[];
    };

/**
 * Resolve one canonical key against the targets it matched.
 *
 * `candidates` must be every `citation-targets` row matching the key. Passing
 * a pre-narrowed list re-introduces exactly the defect this function exists to
 * remove: narrowing IS the decision, and it belongs here.
 *
 * Multiplicity is counted over DOCUMENTS, not rows. One document legitimately
 * holds several rows for the same key (the statute row and its article-section
 * row both answer `abbrev_art:BV/36`), and that is not ambiguity.
 */
export function resolveAgainstTargets(
  normalizedReference: string | null | undefined,
  candidates: CitationTarget[],
): CitationResolution {
  if (!normalizedReference) {
    return { status: 'unresolved', reason: 'not_normalizable', target: null, candidates: [] };
  }

  if (candidates.length === 0) {
    return { status: 'unresolved', reason: 'no_target_in_corpus', target: null, candidates: [] };
  }

  const distinctDocuments = new Set(candidates.map((c) => c.document_id));
  if (distinctDocuments.size > 1) {
    return { status: 'unresolved', reason: 'ambiguous', target: null, candidates };
  }

  // One document, possibly several rows. Prefer the PROVISION-level row: it
  // carries `section_id`/`section_anchor`, so "Art. 36 BV" opens the article
  // rather than a 525KB statute (#573). This is a granularity preference
  // within a single already-decided document, never a choice between norms.
  const target = candidates.find((c) => c.section_id) ?? candidates[0];
  return { status: 'resolved', reason: null, target, candidates };
}
