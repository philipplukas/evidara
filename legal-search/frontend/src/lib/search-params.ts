import { createSearchParamsCache, parseAsArrayOf, parseAsString } from "nuqs/server";

/**
 * Central definition of all URL search params.
 *
 * Single source of truth — used by both client hooks (useQueryState)
 * and server components (searchParamsCache).
 *
 * URL structure: /?q=...&item=...&tab=...&jurisdictions=CH,AT&languages=de
 */
/**
 * The query the app boots with. `HomeClient` runs it on mount, so the results
 * shown on first load are this query's.
 *
 * It lives here because two components read `q` and disagreeing about its default
 * is not a cosmetic bug: `HomeClient` defaulted to this value and ran the search,
 * while `WorkspaceClient` defaulted to `""` and rendered "start a search" over the
 * results — a header claiming a query beside a body saying none had run. It also
 * disabled the retry button and suppressed the auto-search effect, both of which
 * key off the same falsy value (#762).
 */
export const DEFAULT_SEARCH_QUERY = "Art. 754 OR Verantwortlichkeit";

export const searchParamsParsers = {
  /** Search query */
  q: parseAsString.withDefault(DEFAULT_SEARCH_QUERY),
  /** Selected item ID (drives detail panel) */
  item: parseAsString,
  /** Active detail tab */
  tab: parseAsString.withDefault("details"),
  /** Active jurisdiction filters (comma-separated) */
  jurisdictions: parseAsArrayOf(parseAsString, ","),
  /** Active language filters (comma-separated) */
  languages: parseAsArrayOf(parseAsString, ","),
  /** Source type filter */
  sourceType: parseAsString,
};

/**
 * Server-side search params cache.
 * Use in Server Components to read URL state without client-side JS.
 *
 * Usage in page.tsx:
 *   const { q, item } = await searchParamsCache.parse(searchParams);
 */
export const searchParamsCache = createSearchParamsCache(searchParamsParsers);
