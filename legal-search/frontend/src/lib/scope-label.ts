import type { ResultSet } from "./types";

/**
 * Minimal shape of a `next-intl` translator scoped to `results.scope`.
 * Declared structurally so this module stays a pure, testable helper.
 */
export type ScopeTranslator = (key: string, values?: Record<string, string>) => string;

/**
 * Human-readable label for the result set currently on screen.
 *
 * Search scopes are *derived* rather than stored: the workspace reducer is pure
 * and cannot translate, so a stored label is necessarily English and leaks into
 * localized UIs (#648 — `Results for "Präambel"` rendered inside an otherwise
 * fully German workspace). Pivot scopes keep their stored label because the
 * component that dispatches `PIVOT` has a translator and localizes it there.
 */
export function describeResultSetScope(resultSet: ResultSet, t: ScopeTranslator): string {
  if (resultSet.source.type === "search") {
    return t("resultsFor", { query: resultSet.source.query });
  }
  return resultSet.scopeLabel;
}
