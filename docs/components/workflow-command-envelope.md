# WorkflowCommandEnvelope

The envelope every `evidara` workflow command prints on stdout: one JSON object per step,
describing what the step did, what it observed, whether a human is needed, and — the part
that has no equivalent elsewhere — **whether the step can be taken back**.

| Piece | Path | Size |
|---|---|---|
| Contract | [`contracts/schemas/workflow-command-envelope.schema.json`](../../contracts/schemas/workflow-command-envelope.schema.json) | 155 lines, JSON Schema 2020-12 |
| Reference implementation | [`tools/evidara-cli/src/evidara_cli/envelope.py`](../../tools/evidara-cli/src/evidara_cli/envelope.py) | 132 lines, no imports beyond `typing` |
| Worked example | [`contracts/examples/workflow-command-envelope.json`](../../contracts/examples/workflow-command-envelope.json) | validated in CI by `scripts/validate_json_schemas.py` |
| Tests | [`tools/evidara-cli/tests/test_envelope.py`](../../tools/evidara-cli/tests/test_envelope.py) | — |
| Rationale | [ADR-0022](../adr/adr-0022-agentic-cli-workflow-control-surface.md), [architecture note](../architecture/agentic-cli-workflow-architecture.md) | — |

## Purpose

One reporting format for human-gated operational steps, so that an agent, an operator and an
evaluator all read the same object. It carries step identity, an outcome status that includes
`needs_human` as a first-class value, the evidence the step gathered, a non-binding
recommendation — and `side_effect_level`, which is the part with no equivalent in the
frameworks this shape usually gets compared to.

This page exists because the envelope is the one piece of this repo with no domain content in
it at all. That makes it unusually easy to reason about in isolation, but only if the boundary
is written down and guarded; otherwise it drifts into the CLI it happens to live in.

## Current state

Stable and in use. Every `evidara workflow …` and `evidara workflow coverage …` command emits
one. The vocabulary has not changed since ADR-0022.

### `side_effect_level` — the load-bearing idea

Every step declares one of three values. They are **not** a severity scale and not a
permission level. They answer exactly one question:

> If this step has already run, what does the caller have to do to get back to where it
> started?

| Level | Meaning | What the caller does differently |
|---|---|---|
| `none` | The step performed no write. Re-running it changes nothing. | Retry freely, in parallel, without asking. Branch a planner over it. Nothing to undo. |
| `reversible` | The step wrote something, **and a supported corrective action exists**. | Do not retry blind — **compensate first, then retry.** Read `compensation.command`; it is populated precisely when this is true. |
| `irreversible` | The step wrote something with no supported corrective action. | Do not run it without a human decision recorded first. Once it is `passed`, recovery is a new forward action, never an undo. |

Three properties of the definition are worth stating explicitly, because they are where
similar-looking vocabularies usually go wrong:

**It classifies the step's own write, not the state of the world afterwards.** A step can be
`reversible` while its observable consequences are not. Flipping a blueprint template's
`enabled` key off again restores the config; it does not un-send the HTTP requests the live
runs made to a third-party portal in the meantime. The field is about the caller's recovery
path, not about causal innocence — see the note on the enablement flip below, which is the
concrete case where these two readings come apart.

**It is declared, not inferred.** The producer states it; nothing computes it from what the
step turned out to do. That is what makes it usable *before* the step runs — an agent reading
a step's declared level can decide whether to ask, and a `--dry-run` variant of a mutating
command declares `none` truthfully because the dry run really does not write.

**`reversible` is a promise, and `compensation` is how it is kept.** A step that declares
`reversible` and supplies no compensating action has said nothing useful. The two fields
are meant to be read together; ADR-0022's rule that *"reasoning backtracking and side-effect
compensation are distinct"* is the same point — compensation is a real corrective call, not
an in-memory rewind.

#### The cases in this repo that the definitions come from

These are the actual producers, so the vocabulary is anchored to something rather than to a
thought experiment.

**`none` — a preflight that only reads.** `coverage.preflight`
(`tools/evidara-cli/src/evidara_cli/coverage_cmd.py:291`, envelope at `:337` and `:450`)
checks whether a blueprint template *could* be enabled: it reads the template read model, the
provider readiness, and the acceptance-evidence verdict, and writes nothing whatever the
answer is. An agent may run this as often as it likes, and does not have to ask first.

The same reasoning makes a **refusal** `none` even inside a mutating command: when
`coverage.enable` refuses to flip the key, it declares `none` (`coverage_cmd.py:889`) because
nothing was written — *"Refused to flip the config key. Nothing was written."*

**`reversible` — creating a draft.** `workflow source apply`
(`tools/evidara-cli/src/evidara_cli/workflow_cmd.py:310`, envelope at `:370`) creates a draft
source in platform-control. Real write, real corrective action: the envelope carries
`compensation.command = evidara workflow source compensate --source-id …`, and
`workflow source compensate` (`:529`) executes it — cancelling the run via
`POST /v1/runs/{run_id}/cancel` (`platform-control/src/platform_control/routers/runs.py:193`)
and rejecting the pending version. Note that the compensating step is itself `reversible`
(`workflow_cmd.py:626`), which is correct: a cancelled run can be retried
(`routers/runs.py:211` resets it to `PENDING`).

**`reversible` on a failed write, deliberately.** When the enablement `PUT` raises, the error
envelope declares `reversible`, not `none` — `coverage_cmd.py:934`, whose comment says it
plainly: *"The write may or may not have landed, so the envelope must not claim `none`."*
Under uncertainty the field takes the stronger of the two readings. That is the rule: **a
step declares the highest level it might have reached, not the one it hoped for.**

**`irreversible` — declared in the vocabulary, emitted by nothing.** Every `build_envelope`
call site in this repo passes `none` or `reversible`; `irreversible` appears in the schema
enum, in this page, and in the architecture note, and nowhere in any producer. That is a fact
about the repo, not a defect in the schema, but it means the level is defined by its
definition rather than by use — which is why `tests/test_envelope.py` exercises it explicitly.

The obvious candidate is the ADR-0030 config-key flip — `coverage.enable`
(`coverage_cmd.py:776`), the operator act that arms a blueprint template for live acquisition
against a third-party portal. It declares **`reversible`** (`:1034`), and on the definition
above that is right rather than wrong: ADR-0030 §2 makes `enabled: false` an explicit kill
switch, re-read on every dispatch, so flipping it back really does stop the next run — and the
envelope supplies the compensating command (`:1043`). What the flip cannot take back is the
traffic already sent while the key was armed. If a future revision wants that consequence
classified, the honest move is a **second** field for it, not a redefinition of this one:
overloading `side_effect_level` to mean "consequences are permanent" would make it unusable
for the retry/compensate decision it currently drives.

#### What a consumer is expected to do

The three levels plus the five `status` values give an agent loop a policy it can execute
without understanding the domain:

1. `none` → retry or branch freely.
2. `reversible` + not `passed` → run `compensation.command` **before** retrying.
3. `irreversible` → stop and obtain a human decision, whatever `decision.recommended_action`
   says. `decision` is documented in the schema as *"Guidance for agents and humans; not
   final authority"*, and this is the case where that caveat is the whole point.
4. `status: needs_human` → stop regardless of level.

### Strict where it matters, open where the payload lives

The schema is deliberately mixed, and the split is not an accident:

- **Closed** (`additionalProperties: false`): the envelope's own top level, each `evidence`
  item, `decision`, and `compensation`. These are the fields a consumer branches on, so
  extending them is a contract change and a producer may not do it unilaterally. An unknown
  top-level key, an unknown `evidence.kind`, or an extra key on `decision` fails validation.
- **Open** (`additionalProperties: true`): `inputs`, `artifacts`, `error_detail`. These carry
  caller-specific payload. Closing them would make the envelope unusable outside whatever
  domain defined the keys, which is the opposite of the point.

Two consequences worth knowing before writing a consumer:

- **Absent and `null` mean the same thing.** `build_envelope` always emits `run_id`,
  `artifacts`, `evidence`, `decision`, `next_actions` and `compensation` — as `null` when
  unset — but omits `error` and `error_detail` entirely when unset. Both shapes validate.
  Read with `.get()`, not `in`.
- **The builder does not validate.** `status` and `side_effect_level` are plain strings in the
  signature; an unknown value passes straight through and is caught only by the schema. This
  is deliberate: it is what keeps `envelope.py` dependency-free. A consumer that wants
  rejection at construction time validates the result itself.

### What it deliberately does not do

- **It does not enforce anything.** It is a reporting format. The two-key enablement lock
  (ADR-0030) and the refusal codes live in the commands, not in the envelope, and an envelope
  saying `side_effect_level: irreversible` stops nothing on its own.
- **It does not sign or bind evidence to artifacts.** `evidence[]` is assertions a producer
  made about what it saw. There is no attestation, no digest, and no tamper-evidence; if you
  need those, this is the wrong layer.
- **It does not model a workflow.** No graph, no state store, no scheduler, no resumption.
  `run_id` is a correlation string the producer supplies; nothing in this component makes it
  durable.
- **It does not transport.** One JSON object on stdout. No streaming, no partial updates, no
  progress.
- **It does not cover the whole evidence vocabulary in code.** The schema declares five
  `evidence.kind` values; `envelope.py` supplies constructors for three (`http`, `assertion`,
  `count`). `contract` and `object-ref` items are built as literals by callers.

## Source of truth

The **schema** is canonical: `contracts/schemas/workflow-command-envelope.schema.json`. It is
hand-authored (unlike `contracts/api/platform-control.openapi.yaml`, which is generated) and
lives at the monorepo root per ADR-0004, not inside the CLI.

`tools/evidara-cli/src/evidara_cli/envelope.py` is a **reference implementation**, not the
contract. It is a formatter: it does not validate, and it may lag the schema (today it supplies
constructors for three of the five declared `evidence.kind` values). Where the two disagree,
the schema wins.

ADR-0022 is the rationale; `docs/architecture/agentic-cli-workflow-architecture.md` is the
narrative. `contracts/examples/workflow-command-envelope.json` is the worked example, validated
against the schema in CI by `scripts/validate_json_schemas.py`.

## Minimal next tasks

- **Decide whether `irreversible` should have a producer.** Right now it is defined and
  unemitted (see above). Either a step that genuinely has no compensating action gets the
  label, or the level stays a declaration the vocabulary makes available to consumers with
  different steps. Both are defensible; neither is currently written down as a decision.
- **Consider constructors for `contract` and `object-ref` evidence**, so the reference
  implementation covers the whole declared vocabulary rather than three fifths of it.
- Whether this component is ever separated from the repo is a **separate decision** and is not
  taken here. What this page and `test_envelope.py` do is make it a decision rather than a
  project: the boundary is guarded, the tests stand alone, and the couplings are enumerated
  below.

## Later expansion

- **A second field for consequence permanence.** `side_effect_level` answers "can the caller
  undo this step's write". It deliberately does not answer "are this step's effects on the
  outside world permanent" — the ADR-0030 flip is the case where the two answers differ. If
  that second question needs modelling, it needs its own field; overloading this one would
  break the retry/compensate decision it currently drives.
- **Splitting evidence outcomes three ways.** `passed: true | false | null` collapses "checked
  and fine" with "did not run", which is the distinction ADR-0030 §5's `skipped_gates` note is
  about. Any change here is a contract change and belongs with that work, not with this page.

## Dependencies

- **Runtime: none.** `envelope.py` imports `__future__` and `typing`, nothing else — no
  third-party package, no sibling module, no package-level import.
- **Test-only:** `jsonschema` (dev dependency group of `tools/evidara-cli`), used solely to
  validate builder output against the schema.
- **Consumers in this repo:** `tools/evidara-cli/src/evidara_cli/workflow_cmd.py` and
  `coverage_cmd.py`. Both depend on the envelope; the envelope depends on neither.

## Testing

`tools/evidara-cli/tests/test_envelope.py`, run by `bash scripts/check-evidara-cli.sh`. It
covers the component on its own terms rather than through the commands that happen to use it:

- **Boundary:** the module's imports are parsed with `ast` and asserted to stay within
  `{__future__, typing}`; the schema is asserted to contain no `$ref`.
- **Contract conformance:** minimal and fully-populated builder output validate; every declared
  `status` and every declared `side_effect_level` validates — including `irreversible`, which
  nothing in this repo emits and which would otherwise be untested.
- **Boundary cases:** an unknown `side_effect_level` passes the builder and fails the schema; a
  missing one is a `TypeError` at the builder and a validation error at the schema; unknown
  keys are rejected at the top level, on `evidence` items, on `decision` and on `compensation`,
  and accepted inside `inputs`, `artifacts` and `error_detail`.
- **Key presence:** the absent-versus-`null` asymmetry is pinned so it cannot change silently.

The fixture raises rather than skips when the schema file is missing: a contract test that
self-skips reports a pass over nothing.

## Drift risks

The component is domain-free, and that is guarded rather than asserted:

- `envelope.py` imports **only** `__future__` and `typing`. No sibling module, no package
  import, no third-party dependency.
  `test_envelope.py::test_envelope_module_has_no_upward_or_third_party_imports` parses the
  module with `ast` and fails the build if that changes.
- The schema contains no `$ref`, so it resolves without the rest of `contracts/`
  (`test_schema_is_self_contained`).
- The envelope's tests used to live inside `test_workflow_cmd.py`, a module that imports
  `evidara_cli.main`, `evidara_cli.workflow_cmd` and `evidara_cli.proposal` in order to test
  everything else in it — so the envelope could not be tested without the whole CLI. They now
  live in `test_envelope.py`, which imports `evidara_cli.envelope` and the schema and nothing
  else from the package.

What remains coupled, and why it is kept rather than removed:

| Coupling | Where | Decision |
|---|---|---|
| `$id` is `https://evidara.dev/schemas/workflow-command-envelope` | schema `:3` | **Keep.** A `$id` must be a URI the publisher controls. Changing it is a republishing decision, not a cleanup. |
| Description says "returned by every evidara-cli workflow command" | schema `:5` | **Keep.** It is accurate about the current producer. Genericising it now would make the contract describe something that does not exist. |
| Example strings: `source-lifecycle`, `source.inspect`, `platform-control:/v1/sources/src_123`, `evidara workflow source compensate …` | schema `:22`, `:31`, `:74`, `:135` | **Keep and document.** All are inside `description` text, none constrain a value. They are also the only reason the field descriptions are concrete rather than abstract. |
| Module docstring cites `contracts/schemas/…` and ADR-0022 | `envelope.py:3-4` | **Keep.** It is the provenance pointer, and it is what sends a reader here. |
| `jsonschema` in the CLI's dev dependency group | `tools/evidara-cli/pyproject.toml` | **Test-only, deliberately.** The runtime module stays import-free; only the contract test needs a validator. |

Nothing Swiss, nothing legal, nothing about documents, jurisdictions, authorities, corpora,
runs-as-a-domain-object, or providers appears in either file. The verification for that claim
is the import guard above plus the absence of any `$ref`; the wording of the descriptions was
read by hand.

Two further drift risks worth naming:

- **The schema and the reference implementation can disagree silently.** Nothing regenerates
  one from the other. `test_envelope.py` catches disagreement only for the shapes it builds, so
  a new optional field added to the schema and not to `envelope.py` (or the reverse) would go
  unnoticed. Adding a field means touching both, plus
  `contracts/examples/workflow-command-envelope.json`.
- **The `file:line` citations on this page are to producers that move.** They were verified
  against the tree at the time of writing; if one is off by a few lines, trust the symbol name
  over the number.
