# Multi-agent workflows

Scripts for the Claude Code **Workflow** tool. Each one encodes an orchestration — fan out, then
verify adversarially — that was worked out by hand and paid for itself.

**Nothing here has ever been executed.** These scripts are syntax-checked
(`bash .claude/workflows/check-syntax.sh`) and reviewed, and that is all. Treat the first run of
each as a run to supervise, not a run to trust.

Shared conventions live in [`_house-rules.md`](_house-rules.md). Read it before writing a new
script or changing a prompt in an existing one — the rules there are the reason these workflows
find things instead of producing wishlists.

---

## The one idea

Every script has the same spine:

```
fan out over N independent items  →  each finding is re-derived by a different agent  →  rank, cap, report
```

The second arrow is the whole product. A finding that survives only because the agent that made it
believes it is not a finding. Verifiers are prompted to **refute**, and default to refuted when
they cannot reproduce a claim themselves. Absence of proof is refutation, not a tie.

The `pipeline()` shape matters too: verification of dimension A starts as soon as A reports,
without waiting for B. A barrier is used only where a stage genuinely needs all of the previous
stage at once — which, in this catalogue, is nowhere.

## Two families

**Verification** — *given a change, is it right?* Input is a diff, a registry, a set of gates.

**Discovery** — *given a surface, what is weak?* Input is a lens and a path. Same verification
backbone, opposite direction. These are the ones that go wrong most easily: an improvement-finder
with no evidence rule produces "add more tests" and "consider extracting a helper", which costs a
reader more than an empty report. Three rules in every discovery script prevent that: every finding
is anchored to a re-derivable fact, an adversarial stage kills unsupported ones, and the output is
ranked and capped.

---

## Catalogue

Agent counts are **default case**; every script keeps its default under the medium size guidance of
15, and every fan-out that would naturally exceed it reads its batch size from `args`.

| Script | Family | Agents (default) | Touches outside the repo? | Writes to the repo? |
|---|---|---|---|---|
| [`adversarial-pr-review.js`](adversarial-pr-review.js) | verification | 12 | no | mutates + reverts |
| [`provider-conformance-matrix.js`](provider-conformance-matrix.js) | verification | 12 | no | mutates + reverts |
| [`cross-surface-gate-sweep.js`](cross-surface-gate-sweep.js) | verification | ≤14 | no | runs gates; one may regenerate |
| [`cantonal-onboarding-dry-run.js`](cantonal-onboarding-dry-run.js) | verification | 14 | **no — by construction** | no |
| [`claims-vs-enforcement.js`](claims-vs-enforcement.js) | discovery | 14 | no | no |
| [`surface-weakness-sweep.js`](surface-weakness-sweep.js) | discovery | 10 | no | no |
| [`guard-efficacy-mutation.js`](guard-efficacy-mutation.js) | discovery | 12 | no | worktrees only |
| [`visual-critique.js`](visual-critique.js) | discovery | 10 | no | no |

No script in this directory merges a PR, pushes, deletes a branch, comments on a PR, fetches from a
public-sector host, dispatches an acquisition run, or flips a config key. Where a workflow reaches
one of those boundaries it stops and emits a **decision memo** naming what a human must decide.

---

### `adversarial-pr-review.js`

**For:** a PR whose own CI is green and whose change touches behaviour, contracts or guards.

Five dimensions — correctness by re-derivation, tests-that-cannot-fail, contract sync,
docs-vs-code drift, scope discipline — each finding refuted by an independent sceptic that re-runs
the command itself.

**It does not duplicate `/code-review`.** That command is a *diff-reading* review: five agents read
the diff, git blame, prior PR comments and code comments, then a scorer drops anything under 80.
Its own instructions say *"Do not check build signal or attempt to build or typecheck the app"* and
list *"lack of test coverage"* among its false positives. This one runs things. Use both:
`/code-review` for what the diff says, this for what the code does.

**What it would have caught:** a feature that could be deleted entirely with all 286 tests still
passing; a deny-assertion that probed a nonexistent key and so could never fail; an operator
kill-switch flippable with `exit 0`; a change that would have duplicated the federal corpus and
minted another copy at every future consolidation. All four sat in green PRs. None is visible in a
diff.

**Do not use it** for a docs-only or mechanical-rename PR — the mutation dimension has nothing to
break and you will pay twelve agents for it. `args`: `target`, `verifyFanout` (1, raise to 2–3 for
17/22 agents), `topN` (8).

### `provider-conformance-matrix.js`

**For:** after adding or promoting an acquisition provider, or periodically.

Six checks per provider: registry prose vs class attribute, module prose vs class attribute,
readiness declared and fail-closed, capture-guard usage, `in_force_until` reading, and whether any
test would notice the readiness changing.

**What it would have caught mechanically:** #833 — three registry comments describing a readiness
state the classes no longer had, corrected by hand. And #843 — four producers passing the upstream
end-date through unadjusted while one provider's own `is_in_force` treats that date as *exclusive*
and the consumer (`legal-search/api/src/core/norm-hierarchy/in-force.ts`) defines it as *inclusive*.

The gap it fills is precise: `test_blueprint_provider_parity.py` ties templates to
`live_ready_names()`, `test_provider_enablement_lock.py` pins the readiness semantics — and
**nothing asserts that the comment above a `register()` call still describes the class below it.**

**Do not use it** to check whether a provider *works*; it never contacts a host. `args`:
`providersPerAgent` (3 → 12 agents; set 1 for the full 13-way fan-out at 28), `only`.

### `cross-surface-gate-sweep.js`

**For:** a branch spanning surfaces, when a "green" local run needs to be trusted.

Runs each touched surface's **CI-equivalent** gate in parallel and reports `PASS` / `FAIL` /
`DID_NOT_RUN` as three distinct outcomes. Tree-mutating gates (generate-then-diff) are serialized
after the parallel phase, because one owner per OpenAPI file is a constraint on workflows too.

**Why it is not a Makefile:** the hard part is refusing to call a gate that did not run a gate that
passed. `scripts/check-platform-control.sh` *is* the shell script, and it still skips its entire
admin half without comment when `admin/package.json` is absent. Every trap in
[`_house-rules.md §2`](_house-rules.md) reads green while running nothing.

**Note:** `.claude/commands/merge-readiness.md` carries an older, narrower gate table (it prescribes
`cd platform-control && uv run pytest`, which `CLAUDE.md` explicitly calls narrower than CI). This
workflow uses the `CLAUDE.md` table and reports the disagreement rather than silently preferring
one. The command should be updated; that is not this directory's change to make.

**Do not use it** as a CI substitute — it runs on your machine, with your Docker daemon and your
Node. `args`: `all`, `base`, `maxGates` (11 — plus the serialized mutating gate, Select and
Aggregate, that is 14 even on the fallback full-sweep path).

### `cantonal-onboarding-dry-run.js`

**For:** costing the Nth cantonal source — roadmap step 8 in
`docs/architecture/ch-acquisition-coverage-status.md`, "the provider is unchanged, the cost is
config + evidence".

Drafts and validates `lexfind_api` blueprint templates for the 23 cantons that have none, then
emits a decision memo. Eight validations per canton: jurisdiction, entity id, corpus, extractor
profile, language, search shape, compliance policy, ships-shut.

**Read the header comment before changing the fan-out axis.** A measurement that 19 of 22 cantonal
portals serve a byte-identical `robots.txt` suggests fanning out over *portals*. That points at the
`canton_http` provider, and the repo says not to: it is `readiness = SCAFFOLD`, and
`ch-acquisition-coverage-status.md` records it as *"Superseded by LexFind. Do not plan against it"*
— the SPA portals never serve the statute to a deterministic fetch (#631/#716). A shared
`robots.txt` proves a shared CMS, not reachable text.

**The three things it stops at**, each landing in the memo rather than in an action: LexFind's
terms were never confirmed with the Schweizerische Staatsschreiberkonferenz, so nothing contacts
`lexfind.ch`; `entity_ids` is derivable from this repo for exactly three cantons (ZH=26, BE=4,
BS=6) and every other canton is reported BLOCKED rather than given a plausible guess; and
`enabled: true` is the operator's key under ADR-0030. Every drafted template ships
`enabled: false`, and the YAML lives in the memo — **nothing is written to the repo.**

**Do not use it** expecting templates you can merge. It produces reviewable drafts and a precise
blocker list. `args`: `cantonsPerAgent` (4), `cantons`.

### `claims-vs-enforcement.js`

**For:** answering "which of our stated rules are actually load-bearing?"

Harvests invariants from ADRs, `AGENTS.md`/`CLAUDE.md`, architecture docs and load-bearing comments;
for each, locates the enforcing code and the test that would fail if that enforcement were deleted.
Reports only `UNENFORCED`, `UNDER_ENFORCED`, `ENFORCED_BUT_UNTESTED` and `FALSE_CLAIM`.

**The richest seam here**, because this repo writes unusually good comments and prose has no build
step. Four shapes have surfaced: an issue's "non-negotiable" multi-part guard where parts were
delegated elsewhere or absent while the prose read as complete (#731 / `artifact_guard.py`); an ADR
claiming CI enforcement that was real but bucket-granular rather than per-item (ADR-0049) — worse
than none, because the claim reads as covered; an ADR specifying a per-source override lever with no
producer (ADR-0047); and a comment saying `live_ready` was "gone" when `provider_readiness` still
honours it at `src/acquisition_core/providers.py:175`.

It is **read-only**: it *names* the test that should fail. Proving it by breaking the code is
`guard-efficacy-mutation.js`, and the report hands that workflow a list.

**Do not use it** on a deadline — it produces a backlog, not a blocker list. `args`: `batches` (6),
`scope`, `topN` (10).

### `surface-weakness-sweep.js`

**For:** "what is weak in this surface?", by signature rather than by reading everything.

Four lenses, selected with `args.lenses`:

| Lens | Grounded in |
|---|---|
| `dead-declaration` | `delegates_to` mapped with no writer anywhere; `di_overrides.quarantine_min_*` read by DI and emitted by nobody; a `searchParamsCache` documented as the single source of truth with zero consumers in `src/`. A declared-and-empty field reads as *"none exists"*, because OpenSearch returns an empty bucket rather than an error. |
| `silent-degradation` | #631, #675, #713, #728, plus a `logger.debug` swallow that would have silently reverted every production read to a crashing path, and a provenance fallback that substituted the mirror's URL for the source's. |
| `request-path-cost` | a blocking region lookup measured at **4,114 ms** newly on a per-document read path — ~8 s per document fetch — latent only because one env var happened to be set. |
| `frontend-contract` | hardcoded colours where `AGENTS.md` requires `var(--token)`, missing locale keys, props no test renders, exports nothing imports. |

**Why one script and not four:** they differ only in a signature catalogue and a refutation
question. Four near-identical pipelines would be the parallel abstraction `AGENTS.md` rule 3
forbids. The lens is data; the harness is the workflow.

**Do not use it** where a linter already applies — it is for defects no rule expresses. `args`:
`lenses`, `surfaces`, `maxItems` (6), `topN` (8).

### `guard-efficacy-mutation.js`

**For:** finding out whether a surface's tests actually *hold* it, rather than whether they pass.

Deletes or inverts each guard's predicate and reports the ones no test notices. This was the single
most productive technique available: it is what proved a feature was deletable with 286 tests
green, and what proved a deny-assertion could never fail.

**The false positive that would destroy it** — *"I broke it and the tests still passed"* is
worthless if the tests **did not run**. A fresh worktree has no `node_modules` and no populated
virtualenv, and a gate that dies in setup reads as "nothing noticed", which would mark every guard
in the repo as decoration. So the script is built around a **baseline**: each batch runs the gate
unmutated first and must see it green *with a test count*; a batch whose baseline is not green is
abandoned and reported `DID_NOT_RUN`, producing no findings at all. Every mutation is then compared
against that count — a *lower* count is `DID_NOT_RUN`, not "unnoticed". Unnoticed findings are then
reproduced by a second agent in a **fresh** worktree with its own baseline.

**Expensive.** Every mutating agent runs `isolation: 'worktree'` and must install dependencies
inside it. Default is 12 agents and 10 worktrees. Scope it with `args.target`; do not point it at
the repo.

**Do not use it** on a surface whose gate needs infrastructure you do not have — with no Docker
daemon, `legal-search/api`'s integration layer cannot run and every result is inconclusive. `args`:
`target`, `gate`, `batches` (5), `guardsPerBatch` (8).

### `visual-critique.js`

**For:** a design/UX read anchored in rendered output rather than in source.

Reads the ~19 committed PNGs under `legal-search/frontend/e2e/visual.spec.ts-snapshots/` as images
and critiques them against a seven-point rubric — token conformance, render defects, hierarchy,
state coverage, computed contrast ratios, cross-surface consistency, baseline health — with every
source claim cross-checked in the code.

**The defect class it exists for:** a baseline is an assertion about what the product looks like,
and nothing checks whether that assertion is any good. `PROVENANCE.md` records three occasions where
a baseline captured a live bug and shipped it as the definition of correct — a filter rail ~260px
too narrow for ~3.5 months, a retired brand tile for ~3 months, a wrong filter badge blessed five
minutes after the fix landed. None failed CI. The zero-pixel tolerance and the provenance ledger now
check that a baseline is *stable* and *accounted for*; neither checks that it is *right*. A
hand-written critique of these same images found a results region rendering twice at two different
sizes — a real bug, inside a green baseline.

**Do not use it** as an accessibility audit. It says so itself, in a mandatory section: a static
PNG cannot show focus rings, keyboard reachability, hover and transition states, or screen-reader
output — and there is no dark-mode baseline to critique, because the committed files are suffixed
by *platform* (`-linux` / `-darwin`), not by theme. `args`: `snapshotDir`, `groups` (4), `topN` (8).

---

## Rejected, and why

**Docs-vs-code claim audit** — a standalone sweep over `docs/architecture/`, `docs/components/`,
ADRs and READMEs verifying each claim against code. Rejected as redundant from two directions. Its
high-value slice — claims in *changed* docs — is dimension 4 of `adversarial-pr-review.js`, where it
has a trigger and a bounded scope. Its whole-tree slice is strictly weaker than
`claims-vs-enforcement.js`, which asks the harder question: not "is this sentence true?" but "what
enforces it, and what would fail if that enforcement vanished?" A true-but-unenforced claim is the
one that costs you later, and only the second workflow finds it.

**A separate frontend feature-wiring workflow** — folded, not dropped. Its core move ("stub the
line that renders a feature and see whether any gate notices") *is* guard-efficacy mutation with a
frontend catalogue, and lives in `guard-efficacy-mutation.js` via `args.target`. Its static half —
hardcoded colours, missing locale keys, props no test renders — is the `frontend-contract` lens of
`surface-weakness-sweep.js`. A third script would have duplicated both harnesses to add one prompt.

**Per-canton portal onboarding** — rejected on evidence, and the rejection matters more than the
build. Fanning out over cantonal portals targets `canton_http`, which is `SCAFFOLD` and which
`docs/architecture/ch-acquisition-coverage-status.md` records as *"Superseded by LexFind. Do not
plan against it"*. The shared-`robots.txt` measurement establishes a shared CMS; #716 measured that
the statute text is not reachable regardless. `cantonal-onboarding-dry-run.js` fans out over
LexFind entities instead — the same scaling question against a provider that works.

## Known gap

**Design review of routes that have no committed baseline.** `visual-critique.js` can only see what
is in the snapshot directory. Capturing a route at two widths in both themes needs a running app,
and the infrastructure exists — `scripts/playwright-visual-update-docker.sh`, the `run-admin-panel`
skill's prod-build-plus-Playwright recipe, `legal-search/frontend/e2e/helpers/visual-stability.ts`.
Wiring a capture phase in front of the critique is a real, buildable extension. It is deliberately
not in this PR: it would be the first workflow here to start services, and that deserves its own
review rather than riding along. Until it exists, this catalogue says nothing about focus
visibility, keyboard reachability, hover states or dark mode.

## Serialization these workflows must respect

From [`docs/process/max-parallel-execution.md`](../../docs/process/max-parallel-execution.md) and
[`docs/process/parallel-work-streams.md`](../../docs/process/parallel-work-streams.md) — constraints,
not suggestions:

- **One owner per OpenAPI file.** Only one agent per run may regenerate
  `contracts/api/platform-control.openapi.yaml` (it is generated from the FastAPI app, ADR-0034).
  In `adversarial-pr-review.js` that is the contract-sync dimension, and only it.
- **One owner per Alembic migration batch.** No workflow here authors a migration.
- **Same GitHub Actions workflow file → expect conflicts.** No workflow here edits `.github/`.
- **Cross-service behaviour → contract or event schema first.**

The practical rule inside a script: a stage that **mutates** the working tree must never run
concurrently with a stage that **reads** it. Where both are needed, the mutating stage is either
serialized after the parallel one (`cross-surface-gate-sweep.js`) or given `isolation: 'worktree'`
(`guard-efficacy-mutation.js`).

**Do not run two of these at once in the same checkout.** Several run gates or mutate files.

## Authoring a new one

1. Read [`_house-rules.md`](_house-rules.md), then the `workflow-authoring` skill — it is the API
   contract, and a script that does not match it exactly does nothing.
2. `meta` must be a **pure literal**: no variables, no interpolation. `phases[].title` must match
   the `phase()` calls exactly.
3. Default to `pipeline()`. A barrier is justified only when a stage needs *all* of the previous
   stage at once.
4. Keep the default run under 15 agents. If the natural fan-out is larger, read the batch size from
   `args` and document the default here.
5. `bash .claude/workflows/check-syntax.sh` before committing. It wraps each script the way the
   tool does — a bare `node --check` rejects the legal top-level `return` and `await`.
