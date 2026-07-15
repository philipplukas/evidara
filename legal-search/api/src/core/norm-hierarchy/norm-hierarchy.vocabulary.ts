/**
 * The hierarchy of norms (ADR-0033).
 *
 * Nothing in the platform encoded that municipal law sits under cantonal law
 * sits under federal law sits under the constitution — so "can the city ban a
 * certain thing for dogs, year-round?" was not answerable, because answering it
 * IS a hierarchy walk (which cantonal law *delegates* this competence; does
 * federal law *preempt* the field). Those are relations, not text. This module
 * is where the relation lives.
 *
 * Two vocabularies back it, both loaded at module init like the other
 * `contracts/vocabularies/*.json` files (see `core/vocabularies`):
 *
 *   - `norm-level.json`            — the levels and their rank order (curated).
 *   - `jurisdiction-hierarchy.json` — every jurisdiction's level and parent,
 *     GENERATED from platform-control's reference seed by
 *     `scripts/generate_jurisdiction_hierarchy_vocab.py`. platform-control owns
 *     the tree; legal-search reads the build-time export (ADR-0004) rather than
 *     calling it at request time for data that cannot change between deploys.
 *
 * Everything here is a pure function of those two files. The governing chain is
 * NOT stored per jurisdiction — it is a function of `parent` + `level`, and
 * deriving it keeps the 2,169-entry export from also carrying 2,169 chains.
 */
import * as fs from 'node:fs';
import * as path from 'node:path';

const VOCAB_DIR = path.resolve(__dirname, '../../../../../contracts/vocabularies');

function loadVocabFile(filename: string): Record<string, unknown> {
  return JSON.parse(fs.readFileSync(path.join(VOCAB_DIR, filename), 'utf-8'));
}

// ─── norm-level.json ───

export type NormLevel = 'constitutional' | 'international' | 'federal' | 'cantonal' | 'municipal';

/** Level of a *jurisdiction's own* legislation. `constitutional` is never one. */
export type JurisdictionLevel = Exclude<NormLevel, 'constitutional'>;

type NormLevelEntry = {
  rank: number;
  /**
   * Which jurisdiction level enacts norms at this level. Identity for every
   * level except `constitutional`: a constitution is enacted by the *federal*
   * jurisdiction but outranks its ordinary statutes, so it cannot be derived
   * from the jurisdiction and must be declared by the document.
   */
  enactedByJurisdictionLevel: JurisdictionLevel;
  prefLabel: Record<string, string>;
};

const normLevelVocab = loadVocabFile('norm-level.json') as {
  values: Record<NormLevel, NormLevelEntry>;
};

const NORM_LEVELS = normLevelVocab.values;

/** Every norm level, ordered most authoritative first (lowest rank first). */
export const NORM_LEVELS_BY_RANK: NormLevel[] = (Object.keys(NORM_LEVELS) as NormLevel[]).sort(
  (a, b) => NORM_LEVELS[a].rank - NORM_LEVELS[b].rank,
);

/** Lower rank = higher authority. Throws for an unknown level — silently
 * ranking an unmapped level would invert a subordination test. */
export function normLevelRank(level: NormLevel): number {
  const entry = NORM_LEVELS[level];
  if (!entry) throw new Error(`Unknown norm level: ${level}`);
  return entry.rank;
}

export function isNormLevel(value: unknown): value is NormLevel {
  return typeof value === 'string' && value in NORM_LEVELS;
}

export function normLevelLabel(level: NormLevel, locale = 'en'): string {
  const labels = NORM_LEVELS[level]?.prefLabel ?? {};
  return labels[locale] ?? labels.en ?? level;
}

// ─── jurisdiction-hierarchy.json ───

export type JurisdictionNode = {
  jurisdiction_id: string;
  name: string;
  slug: string;
  level: JurisdictionLevel;
  parent: string | null;
};

const hierarchyVocab = loadVocabFile('jurisdiction-hierarchy.json') as {
  values: Record<
    string,
    { name: string; slug: string; level: JurisdictionLevel; parent: string | null }
  >;
};

const JURISDICTIONS = new Map<string, JurisdictionNode>();
const CHILDREN = new Map<string, string[]>();

for (const [jurisdiction_id, entry] of Object.entries(hierarchyVocab.values)) {
  JURISDICTIONS.set(jurisdiction_id, { jurisdiction_id, ...entry });
  if (entry.parent) {
    const siblings = CHILDREN.get(entry.parent) ?? [];
    siblings.push(jurisdiction_id);
    CHILDREN.set(entry.parent, siblings);
  }
}

export function getJurisdiction(jurisdictionId: string): JurisdictionNode | undefined {
  return JURISDICTIONS.get(jurisdictionId);
}

/**
 * The scopes whose law governs `jurisdictionId`, including the jurisdiction
 * itself, ordered most authoritative first.
 *
 * The rule is: every ancestor, plus — for each ancestor and for the
 * jurisdiction itself — its children *at the same level*. That last clause is
 * not a special case for Switzerland; it is what makes the seed's shape work.
 * `jur_ch_federal` (federal) is a CHILD of `jur_ch` (federal), and cantons are
 * *siblings* of `jur_ch_federal`, not its children. Walking parents alone would
 * therefore never reach federal law from a canton — and the whole preemption
 * question (does the TSchG occupy the field?) would be unanswerable. A
 * same-level child is a refinement of its parent's scope, not a tier below it.
 *
 * Returns [] for an unknown jurisdiction — callers must treat that as "we do
 * not have this place" rather than "nothing governs it" (ADR-0033: the agent
 * must be able to refuse).
 */
export function getGoverningScopes(jurisdictionId: string): JurisdictionNode[] {
  const self = JURISDICTIONS.get(jurisdictionId);
  if (!self) return [];

  const collected = new Map<string, JurisdictionNode>();
  const seen = new Set<string>();

  let cursor: JurisdictionNode | undefined = self;
  while (cursor && !seen.has(cursor.jurisdiction_id)) {
    seen.add(cursor.jurisdiction_id);
    collected.set(cursor.jurisdiction_id, cursor);

    for (const childId of CHILDREN.get(cursor.jurisdiction_id) ?? []) {
      const child = JURISDICTIONS.get(childId);
      if (child && child.level === cursor.level) collected.set(childId, child);
    }

    cursor = cursor.parent ? JURISDICTIONS.get(cursor.parent) : undefined;
  }

  return [...collected.values()].sort(
    (a, b) =>
      normLevelRank(a.level) - normLevelRank(b.level) ||
      a.jurisdiction_id.localeCompare(b.jurisdiction_id),
  );
}

/**
 * The document `level` for a set of canonical jurisdiction IDs — sourced from
 * the jurisdiction, never guessed from the text.
 *
 * When a document carries several jurisdictions, the *most specific* one wins
 * (highest rank number): a row tagged both `jur_ch_zh` and `jur_ch` is cantonal
 * law scoped to Switzerland, not federal law.
 *
 * `declaredLevel` — the level the canonical document asserts for itself — wins
 * over the derived one, and only ever moves the norm UP the hierarchy. This is
 * the sole path to `constitutional`: the BV is enacted by `jur_ch_federal` like
 * any statute, so no amount of jurisdiction lookup can tell it apart from the
 * TSchG. Ignoring a declared level that is *lower* than the jurisdiction's own
 * keeps a mislabelled upstream row from demoting federal law to municipal.
 */
export function deriveDocumentLevel(
  jurisdictionIds: readonly string[],
  declaredLevel?: string,
): NormLevel | undefined {
  const derived = jurisdictionIds
    .map((id) => JURISDICTIONS.get(id)?.level)
    .filter((level): level is JurisdictionLevel => level !== undefined)
    .sort((a, b) => normLevelRank(b) - normLevelRank(a))[0];

  if (!isNormLevel(declaredLevel)) return derived;
  if (!derived) return declaredLevel;
  return normLevelRank(declaredLevel) < normLevelRank(derived) ? declaredLevel : derived;
}

/**
 * The jurisdictions whose law outranks a document scoped to `jurisdictionIds` —
 * the `subordinate_to` relation, derived from the tree.
 *
 * A Zurich communal ordinance is subordinate to Zurich cantonal law and to
 * federal law. Note what this is NOT: it is not a document→document edge.
 * Subordination in law is scope-wide — the ordinance is subordinate to the
 * *whole body* of cantonal and federal law, not to some particular act — so the
 * honest edge is document→superior scope. Each scope's own level is recoverable
 * via `getJurisdiction`, so the array stays a flat keyword list.
 */
export function deriveSubordinateTo(jurisdictionIds: readonly string[]): string[] {
  const level = deriveDocumentLevel(jurisdictionIds);
  if (!level) return [];
  const ownRank = normLevelRank(level);

  const superiors = new Map<string, JurisdictionNode>();
  for (const jurisdictionId of jurisdictionIds) {
    for (const scope of getGoverningScopes(jurisdictionId)) {
      if (normLevelRank(scope.level) < ownRank) superiors.set(scope.jurisdiction_id, scope);
    }
  }

  return [...superiors.values()]
    .sort(
      (a, b) =>
        normLevelRank(a.level) - normLevelRank(b.level) ||
        a.jurisdiction_id.localeCompare(b.jurisdiction_id),
    )
    .map((scope) => scope.jurisdiction_id);
}

/**
 * The norm levels that govern `jurisdictionId`, most authoritative first, each
 * with the scopes whose documents sit at that level.
 *
 * `constitutional` resolves through `enactedByJurisdictionLevel` rather than a
 * branch in the code: it maps to the `federal` scopes, so a municipality's
 * hierarchy is constitutional → federal → cantonal → municipal, which is
 * exactly ADR-0033's table.
 */
export function getNormHierarchyLevels(
  jurisdictionId: string,
): { level: NormLevel; rank: number; jurisdictionIds: string[] }[] {
  const scopes = getGoverningScopes(jurisdictionId);
  if (scopes.length === 0) return [];

  const levels: { level: NormLevel; rank: number; jurisdictionIds: string[] }[] = [];
  for (const level of NORM_LEVELS_BY_RANK) {
    const enactedBy = NORM_LEVELS[level].enactedByJurisdictionLevel;
    const jurisdictionIds = scopes
      .filter((scope) => scope.level === enactedBy)
      .map((scope) => scope.jurisdiction_id);
    if (jurisdictionIds.length > 0) {
      levels.push({ level, rank: normLevelRank(level), jurisdictionIds });
    }
  }
  return levels;
}
