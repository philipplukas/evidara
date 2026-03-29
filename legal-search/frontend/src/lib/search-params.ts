import { createSearchParamsCache, parseAsArrayOf, parseAsString } from "nuqs/server";

/**
 * Central definition of all URL search params.
 *
 * Single source of truth — used by both client hooks (useQueryState)
 * and server components (searchParamsCache).
 *
 * URL structure: /?q=...&item=...&tab=...&jurisdictions=CH,AT&languages=de
 */
export const searchParamsParsers = {
  /** Search query */
  q: parseAsString.withDefault(""),
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
