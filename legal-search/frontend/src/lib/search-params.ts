import {
  createSearchParamsCache,
  parseAsArrayOf,
  parseAsBoolean,
  parseAsString,
} from "nuqs/server";

/**
 * Central definition of all URL search params.
 *
 * Single source of truth — used by both client hooks (useQueryState /
 * useQueryStates) and server components (searchParamsCache).
 *
 * URL structure:
 *   /?q=...&item=...&tab=...&jurisdictions=CH,AT&languages=de&sourceType=...
 *    &officialOnly=true&refinements=...
 *
 * **`searchParamsParsers` is the only place a parser for these params may be
 * built.** A call site that writes its own `parseAsString.withDefault(...)`
 * creates a second default for one param, and the two then have to be kept in
 * sync by hand — which is exactly what did not happen. `HomeClient` defaulted
 * `q` to the boot query and ran the search while `WorkspaceClient` defaulted it
 * to `""` and rendered "start a search" over those very results: a header
 * claiming a query beside a body saying none had run, with the retry control
 * disabled and the auto-search effect suppressed off the same falsy value
 * (#762). #763 shared the *constant* rather than the parser, so `AppHeader`
 * kept its own `""` default and the divergence survived the fix (#822).
 *
 * `search-params-single-source.test.ts` enforces this: it fails on any call
 * site outside this module that constructs a parser for a param defined here.
 */

/**
 * The query the app boots with. `HomeClient` runs it on mount, so the results
 * shown on first load are this query's.
 */
export const DEFAULT_SEARCH_QUERY = "Art. 754 OR Verantwortlichkeit";

/** The tab the detail panel opens on when the URL does not name one. */
export const DEFAULT_DETAIL_TAB = "details";

/** Jurisdictions the search is constrained to before the user narrows it. */
export const DEFAULT_JURISDICTIONS = ["CH"];

/** Languages the search is constrained to before the user narrows it. */
export const DEFAULT_LANGUAGES = ["de"];

export const searchParamsParsers = {
  /** Search query */
  q: parseAsString.withDefault(DEFAULT_SEARCH_QUERY),
  /** Selected item ID (drives detail panel) — no selection is a real state. */
  item: parseAsString,
  /** Active detail tab */
  tab: parseAsString.withDefault(DEFAULT_DETAIL_TAB),
  /** Active jurisdiction filters (comma-separated) */
  jurisdictions: parseAsArrayOf(parseAsString, ",").withDefault(DEFAULT_JURISDICTIONS),
  /** Active language filters (comma-separated) */
  languages: parseAsArrayOf(parseAsString, ",").withDefault(DEFAULT_LANGUAGES),
  /** Source type filter */
  sourceType: parseAsString,
  /** Restrict results to official sources */
  officialOnly: parseAsBoolean.withDefault(false),
  /** Serialized ad-hoc refinements applied on top of the context constraints */
  refinements: parseAsString,
};

/**
 * Server-side search params cache.
 * Use in Server Components to read URL state without client-side JS.
 *
 * Usage in page.tsx:
 *   const { q, item } = await searchParamsCache.parse(searchParams);
 */
export const searchParamsCache = createSearchParamsCache(searchParamsParsers);
