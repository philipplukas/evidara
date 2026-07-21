# ADR-0045: The Admin Derives Its Wire Types From the Generated Contract

## Status

Accepted

## Date

2026-07-21

## Context

[ADR-0034](0034-generated-platform-control-contract.md) closed one half of the
loop: `contracts/api/platform-control.openapi.yaml` is now generated from the
FastAPI app and drift-gated by `scripts/check-platform-control.sh`, so the
contract can no longer describe a server that does not exist.

The other half stayed open. `platform-control/admin` is the contract's principal
consumer, and it had **no codegen and no drift gate of its own**. Every wire type
in `src/lib/admin/dataProvider.ts` was hand-declared. Generation protected the
contract *from the server*; nothing propagated it to the client. The gate stopped
one step short of the surface that keeps breaking — the admin shipped both #614
and #616.

By the time #695 was filed the hand-written types had already drifted, and drifted
in the direction that hides bugs — **narrower** than the contract:

| The admin declared | The contract says |
|---|---|
| `total: number` (required) on every list envelope | `RunListResponse` requires only `data`; `total`/`limit`/`offset` are each `integer \| null` |
| `overall_status: "in_progress" \| "blocked" \| "failed" \| "ok"` | `RunPipelineHealthResponse.overall_status` is an open `string` |

A client type narrower than the contract is not a harmless simplification. It
makes the permitted case **unrepresentable**, so the code handling that case looks
dead and goes untested. The `total ?? records.length` fallback — which re-derives
the hit count from the page length, i.e. *the #616 behaviour* — was live in three
places and exercised by none of the 28 data-provider tests, because the type said
`total` could never be missing.

## Decision

**The admin does not hand-write wire types.** They are generated from
`contracts/api/platform-control.openapi.yaml` by `openapi-typescript` into
`src/lib/api/generated/platform-control.ts` and consumed through the `Schemas`
alias in `src/lib/api/schemas.ts`.

`npm run openapi:check` regenerates and fails on a diff, mirroring
`legal-search/frontend`'s gate (ADR-0007). It runs inside `npm run check`, which
`scripts/check-platform-control.sh` already invokes — so the drift gate is in CI
and pre-commit without a new entry point.

`openapi-typescript` rather than `orval`: the admin needs **types only**. Its
transport is react-admin's data provider, not a generated fetch client, and
generating one would create a second, unused HTTP path through the app.

Where a type genuinely cannot be aliased yet — because doing so cascades past the
data provider into form state — it stays hand-written **and is pinned
field-by-field** in `src/lib/api/contract.conformance.ts`. The pin is honest about
its limit: it catches a renamed or retyped field, and it does **not** catch a field
added to the contract. That gap is tracked, not tolerated indefinitely (#737).

## Consequences

**Good.**

- The `total: number` divergence is now a build failure rather than a latent bug.
- Adopting the generated types immediately surfaced two live narrowings the suite
  could not see, one of which (`overall_status`) had a correct runtime fallback
  guarded by a type that claimed it was unreachable.
- ~20 hand-written wire types are retired; the contract is the single source of
  truth end to end, server to browser.

**Costs.**

- The generated file is committed, so contract changes produce a diff in the admin.
  That is the point — the diff is the notification.
- `openapi-typescript` renders open enums as `string` where the Pydantic model has
  no enum. Consumers that want a closed set must narrow **explicitly**, with a type
  guard and a defined fallback, instead of asserting one that the server never
  promised.

## Alternatives considered

- **A runtime validator (zod/valibot) at the fetch boundary.** Catches more — it
  sees actual payloads, not just declared ones — but it is a parallel schema to
  maintain unless also generated, and it does not fail the *build*. Compile-time
  drift detection is the cheaper first line; this remains open as a later addition.
- **Leave the types hand-written and add tests.** This is what the repo had. The
  tests were written against the hand-written types, so they encoded the same
  narrowing. #616 is the demonstration that a suite cannot test a case its types
  forbid.

## References

- ADR-0007 — generated OpenAPI clients in `legal-search/frontend`
- ADR-0034 — the platform-control contract is generated from the app
- #695 — the admin has no OpenAPI drift gate
- #737 — retire the last hand-written wire types
- #614, #616, #618 — the drift bugs this chain closes
