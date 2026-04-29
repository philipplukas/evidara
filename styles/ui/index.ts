/**
 * `@evidara/ui` — shared cross-surface design-system primitives.
 *
 * Companion to `@evidara/tokens` and `@evidara/shell`. Both surfaces
 * (`legal-search/frontend` and `platform-control/admin`) consume this barrel
 * via the path alias declared in their respective `tsconfig.json`:
 *
 *   "@evidara/ui":   ["../../styles/ui"],
 *   "@evidara/ui/*": ["../../styles/ui/*"]
 *
 * Scope: primitives that must render correctly under both token regimes
 * (focus ring, status, button, badge — see ADR-0016 / ADR-0027). Surface-
 * specific cards, shells, and data tables stay in their respective apps.
 *
 * See `styles/ui/README.md` and `docs/adr/0028-shared-shell-module.md` for
 * the rationale (TS-path-alias rather than npm workspace).
 */

export { StatusBadge, type StatusBadgeProps } from "./StatusBadge";
export { STATUS_TOKEN_MAP, type StatusLevel, type StatusTokens } from "./status-tokens";

/**
 * Sentinel value matching the `@evidara/shell` pattern. Cheap regression
 * net the alias-resolution gate-tests on each surface import to confirm the
 * `@evidara/ui` alias resolves end-to-end (tsconfig + vitest + Next bundler
 * all aligned with `next.config.ts` `turbopack.root`).
 */
export const UI_MODULE_VERSION = "0.1.0-status-badge" as const;
