/**
 * Thin re-export shim for historical import paths.
 *
 * Canonical values live in `../tokens/tokens`, which is synced from
 * `/styles/tokens/tokens.ts` via `scripts/sync-tokens.mjs`. Edit the source
 * there and run `npm run tokens:sync`; CI enforces drift.
 */

export * from "../tokens/tokens";
