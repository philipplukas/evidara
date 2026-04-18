/**
 * Canonical React Admin resource names for the platform-control admin.
 *
 * These string values are the routing identifiers React Admin dispatches on —
 * they must match exactly what the HTTP dataProvider expects and what the
 * <Resource name="..."> registrations declare in `AdminApp.tsx`. See issue
 * #272 for the rationale on centralising cross-surface identifiers.
 *
 * When adding a new React Admin resource, extend this map first, then wire
 * the `<Resource>` registration and any dataProvider cases to the exported
 * constant (not a fresh string literal).
 */
export const ResourceName = {
  Jurisdictions: "jurisdictions",
  Authorities: "authorities",
  Sources: "sources",
  PreviewReview: "preview-review",
  Runs: "runs",
} as const;

export type ResourceName = (typeof ResourceName)[keyof typeof ResourceName];
