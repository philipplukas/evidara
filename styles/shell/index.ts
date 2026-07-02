/**
 * `@evidara/shell` — shared cross-surface shell chrome.
 *
 * Companion to `@evidara/tokens`. Both surfaces (`legal-search/frontend` and
 * `platform-control/admin`) consume this barrel via the path alias declared
 * in their respective `tsconfig.json`:
 *
 *   "@evidara/shell":   ["../../styles/shell"],
 *   "@evidara/shell/*": ["../../styles/shell/*"]
 *
 * **Scaffolding-only at intro.** This barrel currently exports a single
 * placeholder marker so both surfaces can prove the path-alias wiring with a
 * real consumer before the first real component lands. The brand-mark
 * unification is owned by a separate PR (#496) and is intentionally not the
 * first migration here.
 *
 * See `docs/adr/0028-shared-shell-module.md` for the rationale and the
 * follow-up plan.
 */

/**
 * Sentinel value the scaffolding gate-tests can import to confirm the
 * `@evidara/shell` alias resolves on each surface. Once the first real shared
 * component lands, this should remain (it's cheap) — the alias guard is
 * useful even after real exports exist.
 */
export const SHELL_MODULE_VERSION = "0.0.0-scaffold" as const;
