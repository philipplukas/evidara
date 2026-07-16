# ADR-0034: Generate the platform-control Contract From the App

## Status

Accepted

## Date

2026-07-16

## Context

`AGENTS.md` states the rule plainly: *"Contract-first. APIs are defined in
`contracts/api/`, not invented inline. The spec is the source of truth."* For
`contracts/api/platform-control.openapi.yaml`, that was not true. The file was
hand-maintained, and hand-maintained files describe the past.

By 2026-07 it had drifted this far from the code (#618):

| The spec said | The code did |
|---|---|
| 4 acquisition provider variants | `AcquisitionProvider` has **11** |
| No `execution_mode` on a source version | Required field |
| List responses are `{data}` | Paginated ones are `{data, limit, offset, total}` |
| `Authorization: Bearer <JWT>`, "from the identity provider" | `X-API-Key`; there is no identity provider |
| 47 paths | 61 |

The drift was not cosmetic — it was **load-bearing in two production bugs**:

- **#614** — the admin's version editor knew the contract's 4 providers, silently
  coerced the other 7 into `firecrawl`, nulled fields like `canton_code`, and
  persisted the corruption with an HTTP 200.
- **#616** — the contract documented list responses without their pagination
  envelope, so the admin concluded the arrays were unbounded, paginated
  client-side, and capped every list at 100 records.

And it **defeated the standard remedy**. The natural fix for #614 is to generate
the provider list instead of hand-writing it. #617 explicitly refused to derive
it from the contract, because the contract was missing the same 7 providers:
generating from it would have reproduced the bug with a generator's blessing.

This is the failure mode of a hand-maintained spec next to a framework that
already emits an accurate one. FastAPI derives `/openapi.json` from the Pydantic
models on every boot. There were two specs; only one was checked against reality,
and it was not the one in `contracts/`.

ADR-0009 already half-admitted this. It says *"Do not hand-edit the generated
spec — change the Pydantic schemas and let FastAPI regenerate it"* and, two lines
earlier, *"The contract spec in `contracts/api/` remains canonical"*, and claims
*"CI validates compatibility using `redocly lint` or `openapi-diff` on the
generated spec"* — a check that never existed. The contradiction was the bug.

## Decision

**`contracts/api/platform-control.openapi.yaml` is generated from the FastAPI app
and gated for drift.**

- `scripts/generate_platform_control_contract.py` imports the app, calls
  `app.openapi()`, and writes it as YAML. `--check` regenerates and fails on any
  difference. It applies **no overlay** — an overlay is a second source of truth,
  which is the thing that broke.
- Everything the document needs that routes and models cannot express —
  title, version, description, tags, operation-id policy — lives in
  `platform_control/openapi.py`. So the served document and the committed one are
  the same bytes.
- `scripts/check-platform-control.sh` runs `--check`. That script is what both
  the `platform-control-check` pre-commit hook and
  `.github/workflows/platform-control.yml` invoke, per the AGENTS.md rule that
  pre-commit and CI run the same checks through `scripts/`.
- `info.version` comes from `platform_control.openapi.API_VERSION` and stays
  pinned to `contracts/manifest.yaml` by `scripts/check_contract_manifest.py`, so
  a contract change remains a versioned event under the existing version-bump
  guard.

This mirrors what `legal-search/frontend` already does with `npm run
openapi:check` (generate + `git diff --exit-code`). The pattern existed in the
repo; it just was not applied here.

### What this does not change

**legal-search stays spec-first.** Its OpenAPI file is hand-authored and its
NestJS decorators are additive (ADR-0008); its clients are generated *from* the
spec by Orval (ADR-0007). That direction is right for legal-search: the spec is a
cross-team interface designed before the code, and there is a real consumer
(the frontend) generated from it.

The two services differ in who the contract is *for*:

| | legal-search | platform-control |
|---|---|---|
| Contract is | a design artifact, agreed before code | a description of an operator API that already exists |
| Written by | humans, first | the framework, from the models |
| Consumers | the frontend, via generated clients | the admin app, the CLI, operators, agents |

Contract-first remains the rule for interfaces designed across a boundary before
they are built. It is the wrong rule for a spec that is *supposed* to describe
what a running service does, because there the code is the fact and the spec is a
copy — and an unchecked copy is a lie waiting to be believed.

## Consequences

**The class of bug is now structurally impossible.** A model change that is not
reflected in the contract fails the build. #614 cannot recur: adding a 12th
`AcquisitionProvider` without regenerating fails `--check`, and
`tests/unit/test_openapi_contract.py` asserts the contract's discriminator
mapping *is* the domain enum. #616 cannot recur: the envelope is in the contract
because it is in the model.

**#617's refusal is now resolvable.** The generated spec carries all 11 variants
with a complete discriminator `mapping` — which the hand-written one lacked even
for its 4. An admin provider list generated from this contract is now correct,
and that follow-up is unblocked.

**The endpoint function name is API surface.** `operationId` is derived from it
(`get_run` → `getRun`) to keep generated clients readable, which preserved all 56
hand-written operationIds. The cost: endpoint function names must be unique
across routers, and renaming one renames its `operationId`.
`tests/unit/test_openapi_contract.py` enforces both.

**The contract can no longer document what the code does not declare.** This is
the point, and it has a price paid in this ADR's own terms:

- ~45 operations lose their hand-written `404`/`409` responses. The exception
  handlers in `main.py` really do produce them, but the routes do not declare
  them, so the export cannot know. Restoring them is per-route work (a list
  endpoint cannot 404) tracked separately — under-documenting is safe, and
  inventing a `404` that cannot happen would be a new lie.
- The four handlers taking a raw `Request` (firecrawl webhook, three DI event
  receivers) document no request body. The old spec's bodies for them were
  unverified prose, and one was already wrong — it never mentioned the Pub/Sub
  push envelope those endpoints accept. Their payload contracts live in
  `contracts/events/*.schema.json`, which is their source of truth anyway.
- `servers` is gone. It was half fiction (`https://platform-control.evidara.dev`
  appears nowhere in `infra/`), and declaring one in the app would aim Swagger
  UI's "Try it out" at it from every deployment. With no `servers`, clients and
  the docs UI resolve against wherever the document was served — which is true.

**Anything else valuable in the old file had to move into the code**, which is
where it should have been: three operation descriptions became endpoint
docstrings, ID-format examples became `Field(examples=...)`, the correction
request examples became `json_schema_extra`, and the ADR-0022 `agent-discovery`
tag — which existed only in the spec — is now on the 15 routes that carry it.

## Alternatives considered

**Keep it hand-written; fix the 7 providers.** Fixes today's drift, not
tomorrow's. The file drifted precisely because nothing forced it not to, and the
next model change starts the clock again.

**Generate, but merge a hand-written overlay for prose and `servers`.** Keeps the
nice-to-haves at the cost of a second source of truth in the generator — the
exact shape of the original bug, in a smaller box.

**Diff the two specs in CI and warn.** A warning is a thing people scroll past.
The drift here survived multiple releases and two bugs while both specs sat in
the same repo.
