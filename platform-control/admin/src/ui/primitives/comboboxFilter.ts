/**
 * Pure search/reporting helpers behind the `<Combobox>` primitive.
 *
 * Split out of the component so the two properties that actually matter can be
 * unit-tested without a DOM:
 *
 *   1. **Diacritic-insensitive matching.** An operator types `zurich`; the
 *      registry says `Zürich`. A picker that only does substring matching on
 *      the raw string makes the milestone's own acquisition jurisdiction
 *      (`jur_ch_zh`) unreachable by typing its name (#666).
 *   2. **Truncation is never silent.** `describeComboboxStatus` is the single
 *      place that turns "how much of the registry am I actually showing?" into
 *      operator-facing words. The bug this replaces rendered 250 of 2,169
 *      jurisdictions in a plain `<select>` with no indication at all that the
 *      list stopped at "Bovernier" — a confident-looking control stating a
 *      value it had not checked.
 */

export type ComboboxChoice = {
  id: string;
  name: string;
};

/**
 * Casefold and strip combining marks so `zurich` matches `Zürich`, `zuerich`
 * notwithstanding (transliteration is out of scope — this only removes
 * diacritics, it does not expand them).
 */
export const normalizeSearchText = (value: string): string =>
  value
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .trim();

export type ComboboxFilterResult = {
  /** The slice actually rendered as options. */
  visible: ComboboxChoice[];
  /** How many choices matched the query in total (may exceed `visible`). */
  matchCount: number;
  /** How many choices were searched. */
  loadedCount: number;
  /** True when `matchCount > limit`, i.e. the option list is a partial view. */
  truncated: boolean;
};

/**
 * Filter `choices` by `query`, ranking prefix matches above interior matches so
 * typing `zur` surfaces `Zürich` ahead of `Oberzurich`. Matches against both the
 * display name and the id, because operators paste ids (`jur_ch_zh`) as often as
 * they type names.
 */
export const filterComboboxChoices = (
  choices: ComboboxChoice[],
  query: string,
  limit: number,
): ComboboxFilterResult => {
  const needle = normalizeSearchText(query);

  if (needle.length === 0) {
    return {
      visible: choices.slice(0, limit),
      matchCount: choices.length,
      loadedCount: choices.length,
      truncated: choices.length > limit,
    };
  }

  const prefixMatches: ComboboxChoice[] = [];
  const interiorMatches: ComboboxChoice[] = [];

  for (const choice of choices) {
    const name = normalizeSearchText(choice.name);
    const id = normalizeSearchText(choice.id);
    if (name.startsWith(needle) || id.startsWith(needle)) {
      prefixMatches.push(choice);
    } else if (name.includes(needle) || id.includes(needle)) {
      interiorMatches.push(choice);
    }
  }

  const matches = [...prefixMatches, ...interiorMatches];
  return {
    visible: matches.slice(0, limit),
    matchCount: matches.length,
    loadedCount: choices.length,
    truncated: matches.length > limit,
  };
};

export type ComboboxStatusInput = {
  query: string;
  matchCount: number;
  visibleCount: number;
  /** Choices held in the browser. */
  loadedCount: number;
  /**
   * Records the server says exist. `undefined` means the list did not report a
   * total — which is reported as unknown rather than assumed equal to
   * `loadedCount`.
   */
  totalCount?: number;
};

/**
 * One sentence describing exactly how much of the registry the operator is
 * looking at. Every branch that is *not* "you can see everything" says so
 * explicitly — there is no state in which this returns a confident-sounding
 * string over a partial list.
 */
export const describeComboboxStatus = ({
  query,
  matchCount,
  visibleCount,
  loadedCount,
  totalCount,
}: ComboboxStatusInput): string => {
  // The fetch itself was short: we are searching a subset of the registry and
  // must never imply otherwise, however few matches came back.
  const fetchIsPartial = typeof totalCount === "number" && totalCount > loadedCount;
  const scope = fetchIsPartial
    ? ` · searching only ${loadedCount} of ${totalCount} records — narrow the search or load more`
    : "";

  if (matchCount === 0) {
    return query.trim().length > 0
      ? `No match for “${query.trim()}” in ${loadedCount} options${scope}`
      : `No options available${scope}`;
  }

  if (visibleCount < matchCount) {
    return `Showing ${visibleCount} of ${matchCount} matches — keep typing to narrow${scope}`;
  }

  if (query.trim().length > 0) {
    return `${matchCount} match${matchCount === 1 ? "" : "es"}${scope}`;
  }

  return `${matchCount} option${matchCount === 1 ? "" : "s"}${scope}`;
};
