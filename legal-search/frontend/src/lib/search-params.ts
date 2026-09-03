import {
  createSearchParamsCache,
  parseAsArrayOf,
  parseAsBoolean,
  parseAsString,
} from "nuqs/server";

/**
 * Central definition of all URL search params.
 *
 * URL structure:
 *   /?q=...&item=...&tab=...&jurisdictions=ch,at&languages=de&sourceType=...
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
 * `search-params-single-source.test.ts` enforces this for every `useQueryState`
 * and `useQueryStates` call site in `src/`. See its docstring for the two
 * evasions it deliberately does not chase.
 *
 * Consumed by the client hooks in `AppHeader`, `HomeClient`, `WorkspaceClient`,
 * `DetailTabs` and `search-constraints-store`. `searchParamsCache` below has no
 * consumer yet — see its own note.
 */

/**
 * The query the app boots with. `HomeClient` runs it on mount, so the results
 * shown on first load are this query's.
 */
export const DEFAULT_SEARCH_QUERY = "Art. 754 OR Verantwortlichkeit";

/** The tab the detail panel opens on when the URL does not name one. */
export const DEFAULT_DETAIL_TAB = "details";

/**
 * Jurisdictions the search is constrained to before the user narrows it.
 *
 * Lower-case, because that is the form the app actually holds: every value
 * entering `SearchConstraintsState` goes through `normalizeJurisdictions`,
 * which lower-cases it. An upper-case `["CH"]` here would parse to a value the
 * store never reports, and — the day a Server Component uses
 * `searchParamsCache` — would render `CH` on the server and hydrate `ch` on the
 * client.
 */
export const DEFAULT_JURISDICTIONS = ["ch"];

/** Languages the search is constrained to before the user narrows it. */
export const DEFAULT_LANGUAGES = ["de"];

export const searchParamsParsers = {
  /**
   * Search query.
   *
   * `clearOnDefault: false` because `q` is the one param the user authors and
   * shares. nuqs otherwise deletes a param whose written value equals the
   * parser default, so searching for `DEFAULT_SEARCH_QUERY` itself would strip
   * `?q=` from the address bar — and the link the user then copies would resolve
   * to whatever `DEFAULT_SEARCH_QUERY` happens to be when it is opened, not to
   * the query they ran. On `main` this could not happen: the only component
   * that writes `q` defaulted it to `""`, which nothing equals (#822).
   */
  q: parseAsString.withDefault(DEFAULT_SEARCH_QUERY).withOptions({ clearOnDefault: false }),
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
 * Server-side search params cache, for reading URL state in a Server Component
 * without client-side JS:
 *
 *   const { q, item } = await searchParamsCache.parse(searchParams);
 *
 * **Nothing consumes this yet.** It is kept because it derives from
 * `searchParamsParsers` above, so a Server Component that adopts it inherits
 * the same defaults the client hooks use rather than inventing its own — which
 * is the whole point of this module. This module's docstring used to claim the
 * cache *was* used by server components while it had no consumer at all; that
 * claim is what let five call sites drift unnoticed (#822).
 */
export const searchParamsCache = createSearchParamsCache(searchParamsParsers);
