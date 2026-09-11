/**
 * Which sub-federal jurisdiction does this query *name*? (#986)
 *
 * #986 measured the thing this module exists for. Against production's
 * 889-document ZH corpus, these two queries score **identically** (14.01):
 *
 *   "Statistikgesetz Kanton Zürich"   -> should ANSWER
 *   "Hundegesetz Kanton Bern"         -> should REFUSE
 *
 * The ZH Hundegesetz genuinely is in the corpus. The second query is wrong
 * about the **canton**, not about the topic — so no relevance score can
 * separate them, and #986 measured the populations overlapping end to end
 * (lowest in-corpus 5.60, highest out-of-corpus 14.01). A score floor fitted to
 * that sample is the fixture trap AGENTS.md names. Refusal here is a *coverage*
 * question — "do I hold the law of the place being asked about?" — and this
 * module answers only the first half of it: which place is being asked about.
 *
 * ## Vocabulary, not a hand-written canton list
 *
 * The names come from `contracts/vocabularies/subdivisions.json` (AGENTS.md
 * rule 2 — grep before you create; the frontend consumes the same file via a
 * generated registry). Each entry is joined to a canonical jurisdiction id
 * through `getJurisdictionBySlug`, so `CH-BE` becomes `jur_ch_be` because the
 * seed says so, not because this file concatenated a string. An entry that does
 * not resolve is dropped — it can then never be detected, and therefore never
 * refused.
 *
 * ## Why this cannot over-refuse
 *
 * The brief for #986 is explicit: **under-refuse, never over-refuse.** A false
 * refusal hides law a user is entitled to, and unlike a false answer the caller
 * cannot detect it. So a name alone is never enough. Half the Swiss cantons are
 * also ordinary words or cities — `Zug` is a train, `Jura` is a mountain range,
 * `Bern`, `Basel`, `Genf`, `Zürich` and `Freiburg` are cities as well as
 * cantons. Detection therefore requires a **tier marker** adjacent to the name
 * ("Kanton Bern", "canton de Berne", "Bern (Kanton)") or the ISO code itself
 * ("CH-BE"). That is positive evidence the query is asking about the *canton*.
 *
 * The cost is deliberate: a bare "Mietrecht Bern" is NOT detected and therefore
 * NOT refused. It behaves exactly as it does today. That is the safe direction.
 */
import * as fs from 'node:fs';
import * as path from 'node:path';
import { getJurisdictionBySlug } from '../norm-hierarchy';

const VOCAB_DIR = path.resolve(__dirname, '../../../../../contracts/vocabularies');

type SubdivisionVocabEntry = {
  country: string;
  prefLabel: Record<string, string>;
  slug: string;
  hierarchyTier: string;
};

/** A sub-federal jurisdiction the query names, resolved to a canonical id. */
export type SubdivisionMention = {
  /** ISO 3166-2 code, e.g. `CH-BE`. */
  isoCode: string;
  /** Canonical platform jurisdiction id, e.g. `jur_ch_be`. */
  jurisdictionId: string;
  /** Display name from the seed, e.g. `Kanton Bern / Canton de Berne`. */
  label: string;
  /** Sub-federal tier from the vocabulary, e.g. `canton`. */
  tier: string;
  /** The text in the query that triggered the match, e.g. `Kanton Bern`. */
  matchedText: string;
};

type MentionCandidate = {
  isoCode: string;
  jurisdictionId: string;
  label: string;
  tier: string;
  /** Folded label token sequences, longest first. */
  labelTokens: string[][];
  /** Precompiled whole-token matcher for the ISO code itself. */
  isoPattern: RegExp;
};

/**
 * Tier markers. Presence of one of these beside a subdivision name is the
 * positive evidence that the query means the *jurisdiction* and not the city or
 * the ordinary word.
 */
const TIER_MARKERS = new Set([
  'kanton',
  'kantons',
  'kantone',
  'kt',
  'canton',
  'cantons',
  'cantone',
  'ct',
  'bundesland',
]);

/** Tokens allowed to sit between a marker and the name ("canton de Berne"). */
const MARKER_FILLERS = new Set(['de', 'du', 'des', 'della', 'del', 'di', 'da', 'of', 'von', 'd']);

/**
 * Fold a string to a comparison form: lowercase, diacritics stripped, and the
 * German ASCII transliterations collapsed, so `Zürich`, `Zuerich` and `Zurich`
 * are one token. Applied to BOTH the query and the vocabulary labels, so the
 * folding can only ever make the two sides agree in the same way.
 */
function fold(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/ae/g, 'a')
    .replace(/oe/g, 'o')
    .replace(/ue/g, 'u')
    .replace(/ß/g, 'ss');
}

/** Split folded text into word tokens. Punctuation and digits are separators. */
function tokenize(folded: string): string[] {
  return folded.split(/[^a-z]+/).filter(Boolean);
}

function loadCandidates(): MentionCandidate[] {
  const raw = JSON.parse(fs.readFileSync(path.join(VOCAB_DIR, 'subdivisions.json'), 'utf-8')) as {
    values: Record<string, SubdivisionVocabEntry>;
  };

  const candidates: MentionCandidate[] = [];
  for (const [isoCode, entry] of Object.entries(raw.values)) {
    // The join is `country` + `slug` — exactly how platform-control's seed
    // builds the jurisdiction slug. No id is constructed here.
    const node = getJurisdictionBySlug(`${entry.country}-${entry.slug}`);
    if (!node) continue;

    const labelTokens: string[][] = [];
    const seen = new Set<string>();
    for (const label of Object.values(entry.prefLabel ?? {})) {
      // A label can carry several names for the same place
      // ("Kanton Bern / Canton de Berne"); each half is a name in its own right.
      for (const part of label.split('/')) {
        const tokens = tokenize(fold(part)).filter((token) => !TIER_MARKERS.has(token));
        if (tokens.length === 0) continue;
        const key = tokens.join(' ');
        if (seen.has(key)) continue;
        seen.add(key);
        labelTokens.push(tokens);
      }
    }
    if (labelTokens.length === 0) continue;
    labelTokens.sort((a, b) => b.length - a.length);

    candidates.push({
      isoCode,
      jurisdictionId: node.jurisdiction_id,
      label: node.name,
      tier: entry.hierarchyTier,
      labelTokens,
      isoPattern: new RegExp(`(?:^|[^a-z0-9])${fold(isoCode)}(?![a-z0-9])`),
    });
  }
  return candidates;
}

const CANDIDATES = loadCandidates();

/** Every subdivision this module is able to detect. Exported for tests. */
export function detectableSubdivisions(): readonly { isoCode: string; jurisdictionId: string }[] {
  return CANDIDATES.map(({ isoCode, jurisdictionId }) => ({ isoCode, jurisdictionId }));
}

function matchesAt(tokens: string[], at: number, label: string[]): boolean {
  for (let offset = 0; offset < label.length; offset++) {
    if (tokens[at + offset] !== label[offset]) return false;
  }
  return true;
}

/**
 * Is there a tier marker immediately before `start` (allowing one filler word)
 * or immediately after `end`?
 */
function hasAdjacentMarker(tokens: string[], start: number, end: number): boolean {
  const before = tokens[start - 1];
  if (before && TIER_MARKERS.has(before)) return true;
  if (before && MARKER_FILLERS.has(before)) {
    const beforeThat = tokens[start - 2];
    if (beforeThat && TIER_MARKERS.has(beforeThat)) return true;
  }
  const after = tokens[end + 1];
  if (after && TIER_MARKERS.has(after)) return true;
  return false;
}

/**
 * The sub-federal jurisdictions this query names, deduplicated.
 *
 * Empty means "the query names none" — which is NOT the same as "the query
 * names one we do not hold", and callers must not conflate them. Only a
 * non-empty result is evidence of anything.
 */
export function detectSubdivisionMentions(query: string): SubdivisionMention[] {
  if (!query || query.trim().length === 0) return [];

  const folded = fold(query);
  const tokens = tokenize(folded);
  const found = new Map<string, SubdivisionMention>();

  for (const candidate of CANDIDATES) {
    // Form 1: the ISO code itself ("CH-BE"). Unambiguous on its own — nobody
    // writes `ch-be` meaning anything but the canton.
    if (candidate.isoPattern.test(folded)) {
      found.set(candidate.jurisdictionId, {
        isoCode: candidate.isoCode,
        jurisdictionId: candidate.jurisdictionId,
        label: candidate.label,
        tier: candidate.tier,
        matchedText: candidate.isoCode,
      });
      continue;
    }

    // Form 2: the name, with a tier marker beside it.
    let matched = false;
    for (const label of candidate.labelTokens) {
      for (let index = 0; index + label.length <= tokens.length && !matched; index++) {
        if (!matchesAt(tokens, index, label)) continue;
        if (!hasAdjacentMarker(tokens, index, index + label.length - 1)) continue;
        found.set(candidate.jurisdictionId, {
          isoCode: candidate.isoCode,
          jurisdictionId: candidate.jurisdictionId,
          label: candidate.label,
          tier: candidate.tier,
          matchedText: tokens.slice(index, index + label.length).join(' '),
        });
        matched = true;
      }
      if (matched) break;
    }
  }

  return [...found.values()];
}
