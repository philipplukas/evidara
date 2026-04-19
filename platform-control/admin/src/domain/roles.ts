/**
 * Canonical user-role identifiers recognised by the admin access-control
 * layer. The string values flow through `NEXT_PUBLIC_USER_ROLE` and
 * `NEXT_PUBLIC_ADMIN_ALLOWED_ROLES`, and are compared case-insensitively
 * after `normalizeRole` (see `src/lib/admin/accessControl.ts`).
 *
 * Keep values lowercase: `normalizeRole` lower-cases before comparing, so
 * a mixed-case constant here would compare unequal to itself.
 *
 * See issue #272 for the cross-surface identifier rationale.
 */
export const Role = {
  Admin: "admin",
} as const;

export type Role = (typeof Role)[keyof typeof Role];
