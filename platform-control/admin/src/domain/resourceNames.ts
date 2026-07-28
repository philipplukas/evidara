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
  BlueprintTemplates: "blueprint-templates",
  PreviewReview: "preview-review",
  Runs: "runs",
  Corrections: "corrections",
  CommentaryInsights: "commentary-insights",
  // Acquisition coverage, NOT "coverage": legal-search serves its own /v1/coverage
  // (what the corpus holds). This is the other half of the ADR-0042 §4 split —
  // what we were asked to acquire, and whether it succeeded.
  AcquisitionCoverage: "acquisition-coverage",
} as const;

export type ResourceName = (typeof ResourceName)[keyof typeof ResourceName];
