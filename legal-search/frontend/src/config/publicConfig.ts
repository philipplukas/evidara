/**
 * Typed, single-source-of-truth config for the legal-search frontend.
 *
 * Rules (see issue #270):
 * - Raw `process.env.*` is read exactly once, here.
 * - Normalization (trimming, URL defaults, enum parsing) happens exactly once, here.
 * - The rest of the app imports canonical names from this module; it must NOT
 *   reach into `process.env` directly.
 *
 * Designated env-reading boundaries in this package:
 * - `src/config/publicConfig.ts` (this file)
 * - `next.config.ts` (Next.js build-time config; inlines NEXT_PUBLIC_* into the bundle)
 * - `playwright.config.ts` and `e2e/*.spec.ts` (test-runner config, not shipped with the app)
 *
 * Note: every value exposed here is sourced from a `NEXT_PUBLIC_*` variable, so
 * each is available on both the server and the browser. That is intentional —
 * these values drive cross-surface handoff (control plane, legal-search BFF,
 * hosted docs) and need to be consistent between SSR and CSR.
 *
 * The module parses the environment once at import time into `publicConfig`.
 * `NEXT_PUBLIC_*` vars are inlined by Next.js at build time, so this is not a
 * runtime env read — it is essentially a typed view over a build-time constant.
 * For unit tests, `buildPublicConfig` is exported so parsing/default behavior
 * can be exercised without mutating `process.env`.
 */

export type PublicConfig = {
  /**
   * BFF base URL used by the in-app fetch mutator and by the Next.js
   * rewrite middleware. Defaults to the local NestJS dev server.
   * Canonical name for `NEXT_PUBLIC_API_URL`.
   */
  apiBaseUrl: string;

  /**
   * Base URL of the platform-control admin surface, exposed as the
   * cross-surface "control plane" entry from legal-search. When unset,
   * the entry is hidden.
   * Canonical name for `NEXT_PUBLIC_CONTROL_PANEL_URL`.
   */
  controlPanelBaseUrl: string | undefined;

  /**
   * Default UI profile used when no per-user cookie is set. Drives whether
   * the control-plane entry is visible on first load.
   * Canonical name for `NEXT_PUBLIC_DEFAULT_UI_PROFILE`.
   *
   * Left as a raw (trimmed) string here; `computeShowControlPlaneEntry`
   * already owns the tolerant normalization (admin/operator/standard/...).
   */
  defaultUiProfile: string | undefined;

  /**
   * Root of the hosted operator documentation site (e.g. MkDocs). When set,
   * the `/docs` page renders a link to `${docsBaseUrl}/`.
   * Canonical name for `NEXT_PUBLIC_EVIDARA_DOCS_BASE_URL`.
   *
   * Normalized with trailing slash removed so call sites can safely
   * template `${docsBaseUrl}/...` without worrying about `//`.
   */
  docsBaseUrl: string | undefined;
};

export const DEFAULT_API_BASE_URL = "http://localhost:3102";

/**
 * Subset of the environment consumed by the frontend. Narrowed so the
 * builder can be exercised from tests without touching the global `process`.
 */
export type PublicConfigEnv = {
  NEXT_PUBLIC_API_URL?: string | undefined;
  NEXT_PUBLIC_CONTROL_PANEL_URL?: string | undefined;
  NEXT_PUBLIC_DEFAULT_UI_PROFILE?: string | undefined;
  NEXT_PUBLIC_EVIDARA_DOCS_BASE_URL?: string | undefined;
};

function normalizeOptionalString(raw: string | undefined): string | undefined {
  const trimmed = raw?.trim();
  return trimmed && trimmed.length > 0 ? trimmed : undefined;
}

function stripTrailingSlash(value: string | undefined): string | undefined {
  if (typeof value !== "string") {
    return undefined;
  }
  return value.replace(/\/$/, "");
}

/**
 * Pure builder: parse a `PublicConfigEnv` snapshot into a `PublicConfig`.
 * Prefer importing `publicConfig` directly; this is exported for tests only.
 */
export function buildPublicConfig(env: PublicConfigEnv): PublicConfig {
  return {
    apiBaseUrl: normalizeOptionalString(env.NEXT_PUBLIC_API_URL) ?? DEFAULT_API_BASE_URL,
    controlPanelBaseUrl: normalizeOptionalString(env.NEXT_PUBLIC_CONTROL_PANEL_URL),
    defaultUiProfile: normalizeOptionalString(env.NEXT_PUBLIC_DEFAULT_UI_PROFILE),
    docsBaseUrl: stripTrailingSlash(normalizeOptionalString(env.NEXT_PUBLIC_EVIDARA_DOCS_BASE_URL)),
  };
}

export const publicConfig: PublicConfig = buildPublicConfig({
  NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  NEXT_PUBLIC_CONTROL_PANEL_URL: process.env.NEXT_PUBLIC_CONTROL_PANEL_URL,
  NEXT_PUBLIC_DEFAULT_UI_PROFILE: process.env.NEXT_PUBLIC_DEFAULT_UI_PROFILE,
  NEXT_PUBLIC_EVIDARA_DOCS_BASE_URL: process.env.NEXT_PUBLIC_EVIDARA_DOCS_BASE_URL,
});
