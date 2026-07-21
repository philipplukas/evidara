import type { components } from "./generated/platform-control";

/**
 * The platform-control wire schemas, as the server actually generates them.
 *
 * `contracts/api/platform-control.openapi.yaml` is generated from the FastAPI
 * app (ADR-0034) and drift-gated by `scripts/check-platform-control.sh`. This
 * module is the second half of that chain: `npm run openapi:generate` renders
 * the contract into `generated/platform-control.ts`, and `npm run openapi:check`
 * fails the build when the checked-in output and the contract disagree.
 *
 * Before this existed the admin hand-declared every wire type, and had already
 * drifted narrower than the contract in exactly the place that caused #616 —
 * `total` was declared `number` where the server may send `null`. Prefer an
 * alias of `Schemas[...]` over a hand-written shape (AGENTS.md rule 4); a
 * hand-written type here is a divergence nothing can detect.
 */
export type Schemas = components["schemas"];
