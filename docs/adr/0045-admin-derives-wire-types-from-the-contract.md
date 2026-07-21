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

There is no hand-written wire type left. #695 landed with three exceptions —
`RunBase`, `RunListItem`, `SourceVersion` — pinned field-by-field in a
`contract.conformance.ts` that could catch a rename or a retype but not an added
field. #737 aliased all three and deleted that file. A pin is a stopgap for a
change in flight, not a resting place: the fields it could not see (`scope`,
`replay`, `refused`, `execution_mode`) were exactly the ones missing.

## Consequences

**Good.**

- The `total: number` divergence is now a build failure rather than a latent bug.
- Adopting the generated types immediately surfaced two live narrowings the suite
  could not see, one of which (`overall_status`) had a correct runtime fallback
  guarded by a type that claimed it was unreachable.
- ~20 hand-written wire types are retired; the contract is the single source of
  truth end to end, server to browser.
- The `AcquisitionSpec` union is the contract's **eleven** providers, not the
  **four** the version dialog renders widgets for. Conflating those two is #614.
  Editability is now an explicit, separate concept (`EDITABLE_PROVIDERS`), so a
  provider the form cannot edit is *unrenderable*, never *unrepresentable* — and
  the `as unknown as AcquisitionSpec` casts that hid real `canton_http` payloads
  in tests are gone.

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
