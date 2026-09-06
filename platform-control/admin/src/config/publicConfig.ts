/**
 * Public (NEXT_PUBLIC_*) config boundary for the platform-control admin.
 *
 * This module is the single place where `NEXT_PUBLIC_*` env vars are read
 * and normalized. It mirrors the boundary-driven config pattern that the
 * NestJS API (`legal-search/api`) uses via `@nestjs/config` (see ADR-0008).
 *
 * Rules:
 *   - App code imports canonical internal names (e.g. `legalSearchBaseUrl`),
 *     never `process.env.NEXT_PUBLIC_*` directly.
 *   - External `NEXT_PUBLIC_*` names are the public contract and must not
 *     be renamed here.
 *   - Normalization (trim, split, default) happens once, at read time.
 *
 * `src/middleware.ts` remains a documented framework-boundary exception
 * because it runs in the edge runtime and reads the server-only
 * `PLATFORM_CONTROL_API_URL`, not a `NEXT_PUBLIC_*` var.
 */

import { parseAllowedRoles } from "../lib/admin/accessControl";

/** Default local legal-search origin preserved from historical call-site defaults. */
export const DEFAULT_LEGAL_SEARCH_BASE_URL = "http://localhost:3101";
/** Default allowed-roles list used when the env var is unset. */
export const DEFAULT_ADMIN_ALLOWED_ROLES_RAW = "admin";

export type PublicConfig = {
  /**
   * Base URL for the legal-search frontend (cross-surface link and
   * handoff). Always set — falls back to DEFAULT_LEGAL_SEARCH_BASE_URL.
   */
  readonly legalSearchBaseUrl: string;
  /**
   * Trimmed `NEXT_PUBLIC_LEGAL_SEARCH_URL` or `undefined` when unset or
   * whitespace-only. Use this when the UI must distinguish "configured" vs.
   * "unconfigured" (e.g. to hide a cross-surface link rather than link to
   * localhost). Use `legalSearchBaseUrl` when a default is desired.
   */
  readonly legalSearchBaseUrlOrUndefined: string | undefined;
  /**
   * Trimmed `NEXT_PUBLIC_MINIO_CONSOLE_URL`, or `undefined` when unset.
   *
   * Deliberately has NO default. The MinIO console is tailnet-only
   * (`minio-evidara.ts.veyo.dev`), so there is no origin that is correct for
   * every deployment — and a wrong one produces a link that asserts the object
   * is reachable when it is not. Consumers render plain text when this is
   * unset; see `resources/runs/runDeepLinks.ts`.
   */
  readonly minioConsoleBaseUrl: string | undefined;
  /**
   * Raw fallback user role (pre-normalization). The consumer calls
   * `normalizeRole` — kept as passthrough so that module stays the single
   * source of truth for role normalization.
   */
  readonly defaultUserRole: string | undefined;
  /**
   * Parsed allowed-roles list (comma-separated NEXT_PUBLIC_ADMIN_ALLOWED_ROLES,
   * trimmed, lowercased, empties filtered). Defaults to `["admin"]` when the
   * env var is unset; may be empty if a non-empty string parses to nothing
   * (e.g. ", , ") — the consumer treats empty as allow-all, matching prior
   * behavior.
   */
  readonly adminAllowedRoles: readonly string[];
  /**
   * Commit SHA this bundle was built from (`NEXT_PUBLIC_BUILD_SHA`), or
   * `undefined` outside a released image. No default: an invented version is
   * worse than none, because it looks like an answer.
   */
  readonly buildSha: string | undefined;
  /** RFC 3339 UTC build timestamp (`NEXT_PUBLIC_BUILD_DATE`), or `undefined`. */
  readonly buildDate: string | undefined;
};

function trimToUndefined(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
}

/** Minimal env-like source used by the config factory — avoids depending on `NodeJS.ProcessEnv`. */
export type EnvSource = Readonly<Record<string, string | undefined>>;

/**
 * Build a `PublicConfig` from an env-like source. Exported for tests; the
 * module-level `publicConfig` passes an explicit literal snapshot (see below).
 */
export function buildPublicConfig(env: EnvSource = process.env): PublicConfig {
  const legalSearchBaseUrlOrUndefined = trimToUndefined(env.NEXT_PUBLIC_LEGAL_SEARCH_URL);
  const legalSearchBaseUrl = legalSearchBaseUrlOrUndefined ?? DEFAULT_LEGAL_SEARCH_BASE_URL;

  // Historical call site: `parseAllowedRoles(env ?? "admin")`. `??` treats
  // empty string as set, so an explicitly empty env would produce `[]`.
  // Preserve that exactly.
  const rawAllowedRoles = env.NEXT_PUBLIC_ADMIN_ALLOWED_ROLES ?? DEFAULT_ADMIN_ALLOWED_ROLES_RAW;

  return {
    legalSearchBaseUrl,
    legalSearchBaseUrlOrUndefined,
    minioConsoleBaseUrl: trimToUndefined(env.NEXT_PUBLIC_MINIO_CONSOLE_URL),
    defaultUserRole: env.NEXT_PUBLIC_USER_ROLE,
    buildSha: trimToUndefined(env.NEXT_PUBLIC_BUILD_SHA),
    buildDate: trimToUndefined(env.NEXT_PUBLIC_BUILD_DATE),
    adminAllowedRoles: parseAllowedRoles(rawAllowedRoles),
  };
}

/**
 * Literal `process.env.NEXT_PUBLIC_*` snapshot.
 *
 * CRITICAL: these must be spelled as literal member expressions here, not read
 * via a variable (e.g. `env.NEXT_PUBLIC_USER_ROLE`). Next.js only substitutes
 * `NEXT_PUBLIC_*` values into the *client* bundle when it sees the literal
 * `process.env.NEXT_PUBLIC_FOO` at build time. Passing `process.env` through
 * `buildPublicConfig`'s default parameter and dereferencing it dynamically
 * left every value `undefined` in the browser — which silently broke the
 * client-side admin access gate (`defaultUserRole` → `""` → 403) regardless of
 * the Docker `ENV NEXT_PUBLIC_USER_ROLE=admin` bake, since that bake only
 * populates the server runtime. Building the module-level config from this
 * literal snapshot is what makes the bake reach the browser.
 */
const NEXT_PUBLIC_ENV: EnvSource = {
  NEXT_PUBLIC_LEGAL_SEARCH_URL: process.env.NEXT_PUBLIC_LEGAL_SEARCH_URL,
  NEXT_PUBLIC_MINIO_CONSOLE_URL: process.env.NEXT_PUBLIC_MINIO_CONSOLE_URL,
  NEXT_PUBLIC_BUILD_SHA: process.env.NEXT_PUBLIC_BUILD_SHA,
  NEXT_PUBLIC_BUILD_DATE: process.env.NEXT_PUBLIC_BUILD_DATE,
  NEXT_PUBLIC_USER_ROLE: process.env.NEXT_PUBLIC_USER_ROLE,
  NEXT_PUBLIC_ADMIN_ALLOWED_ROLES: process.env.NEXT_PUBLIC_ADMIN_ALLOWED_ROLES,
};

export const publicConfig: PublicConfig = buildPublicConfig(NEXT_PUBLIC_ENV);
