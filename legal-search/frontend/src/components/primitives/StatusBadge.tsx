/**
 * Workspace re-export shim. Canonical `StatusBadge` lives in `@evidara/ui`
 * (`styles/ui/StatusBadge.tsx`) and is shared with `platform-control/admin`
 * via the `@evidara/ui` path alias — see ADR-0028 / ADR-0027.
 *
 * Existing imports through `@/components/primitives` and the deep-import
 * `@/components/primitives/StatusBadge` continue to resolve unchanged.
 */
export { StatusBadge, type StatusBadgeProps } from "@evidara/ui";
