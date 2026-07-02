/**
 * Workspace re-export shim. Canonical status tokens live in `@evidara/ui`
 * (`styles/ui/status-tokens.ts`) and are shared with `platform-control/admin`
 * via the `@evidara/ui` path alias — see ADR-0028.
 *
 * Existing imports through `@/lib/status-tokens` continue to resolve
 * unchanged.
 */
export {
  STATUS_TOKEN_MAP,
  type StatusLevel,
  type StatusTokens,
} from "@evidara/ui";
