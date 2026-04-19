/**
 * Canonical query-parameter keys used when legal-search hands off an
 * operator session to the control-plane admin, and the origin discriminator
 * value written into the `from` parameter on that handoff.
 *
 * These keys form part of the URL contract between the two surfaces, so any
 * change must be coordinated with the legal-search frontend that produces
 * them (`from=legal-search&ls_return_to=...&ls_query=...`). See issue #272
 * for the cross-surface identifier rationale and `navigationContext.ts` for
 * the single consumer today.
 */
export const NavigationParam = {
  HandoffOrigin: "from",
  HandoffReturnTo: "ls_return_to",
  HandoffQuery: "ls_query",
  HandoffScope: "ls_scope",
  HandoffItem: "ls_item",
} as const;

export type NavigationParam = (typeof NavigationParam)[keyof typeof NavigationParam];

/**
 * Value written into `NavigationParam.HandoffOrigin` by legal-search when it
 * redirects an operator into the control plane. Matching this string is how
 * the admin surface knows a handoff is in progress and should render the
 * "Return to legal search" affordances.
 */
export const HandoffOriginValue = {
  LegalSearch: "legal-search",
} as const;

export type HandoffOriginValue = (typeof HandoffOriginValue)[keyof typeof HandoffOriginValue];
