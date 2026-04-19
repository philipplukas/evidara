/**
 * Public (NEXT_PUBLIC_*) config boundary for the legal-search frontend.
 *
 * This module is the single place where `NEXT_PUBLIC_*` env vars are read
 * and normalized. It mirrors the boundary-driven config pattern that the
 * NestJS API (`legal-search/api`) uses via `@nestjs/config` (see ADR-0008).
 *
 * Rules:
 *   - App code imports canonical internal names (e.g. `apiBaseUrl`), never
 *     `process.env.NEXT_PUBLIC_*` directly.
 *   - External `NEXT_PUBLIC_*` names are the public contract and must not
 *     be renamed here.
 *   - Normalization (trim, default) happens once, at read time.
 *
 * `next.config.ts` and `src/middleware.ts` remain documented framework-
 * boundary exceptions — Next evaluates them in contexts where importing
 * this module is either impractical (next.config.ts runs before the app
 * graph is resolved) or would widen the edge runtime bundle unnecessarily
 * (middleware). Both still fall back to the same defaults exposed here so
 * behavior stays identical.
 */

/** Default local API base preserved from historical call-site defaults. */
export const DEFAULT_API_BASE_URL = "http://localhost:3102";
/** Default local legal-search frontend origin used for the self-handoff fallback. */
export const DEFAULT_LEGAL_SEARCH_BASE_URL = "http://localhost:3101";

export type PublicConfig = {
  /** Base URL for the legal-search NestJS API. */
  readonly apiBaseUrl: string;
  /** Base URL for the platform-control admin (control panel). Undefined disables the entry. */
  readonly controlPanelBaseUrl: string | undefined;
  /** Raw default UI profile string. Normalization is handled by the consumer. */
  readonly defaultUiProfile: string | undefined;
  /** Base URL for the legal-search frontend (self-reference, used for handoff). */
  readonly legalSearchBaseUrl: string;
  /** Base URL for hosted MkDocs docs. Empty string when unset. */
  readonly docsBaseUrl: string;
};

function trimToUndefined(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
}

/** Minimal env-like source used by the config factory — avoids depending on `NodeJS.ProcessEnv`. */
export type EnvSource = Readonly<Record<string, string | undefined>>;

/**
 * Build a `PublicConfig` from an env-like source. Exported for tests; the
 * module-level `publicConfig` uses `process.env`.
 */
export function buildPublicConfig(env: EnvSource = process.env): PublicConfig {
  // Historical call sites used `env.NEXT_PUBLIC_API_URL ?? fallback` with no
  // trim. Preserve that exactly so a value like " http://host " stays as-is —
  // any change here would be a silent behavior change.
  // TODO(#270): consider also trimming once we confirm no deployment
  // relies on the untrimmed form.
  const apiBaseUrl = env.NEXT_PUBLIC_API_URL ?? DEFAULT_API_BASE_URL;

  // Historical behavior for docs base: when set, strip a single trailing
  // slash; when unset or not a string, fall back to empty string (callers
  // use truthiness to decide whether to render the docs link).
  const rawDocsBaseUrl = env.NEXT_PUBLIC_EVIDARA_DOCS_BASE_URL;
  const docsBaseUrl = typeof rawDocsBaseUrl === "string" ? rawDocsBaseUrl.replace(/\/$/, "") : "";

  return {
    apiBaseUrl,
    controlPanelBaseUrl: trimToUndefined(env.NEXT_PUBLIC_CONTROL_PANEL_URL),
    // Intentionally not trimmed — `computeShowControlPlaneEntry` owns the
    // profile normalization and keeping passthrough here preserves that
    // single-source-of-truth contract.
    defaultUiProfile: env.NEXT_PUBLIC_DEFAULT_UI_PROFILE,
    legalSearchBaseUrl:
      trimToUndefined(env.NEXT_PUBLIC_LEGAL_SEARCH_URL) ?? DEFAULT_LEGAL_SEARCH_BASE_URL,
    docsBaseUrl,
  };
}

export const publicConfig: PublicConfig = buildPublicConfig();
