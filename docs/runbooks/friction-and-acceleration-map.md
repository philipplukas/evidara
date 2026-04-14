# Friction and Acceleration Map

Owner: Platform / GA
Last reviewed: 2026-04-14
Last verified: 2026-04-14
Applies to: CH / AT fast loops, GA evidence assembly, and operator-scale execution

## Purpose

This note captures the main sources of friction we have now that the CH and AT fast loops are
working end to end. It is not another architecture proposal. It is a prioritization tool for:

- reducing human toil
- tightening quality gates
- automating the repetitive evidence/deploy/run loop
- using AI where it accelerates operators without becoming the source of truth

Use this as the bridge between:

- [GA operator board](ga-operator-board.md)
- [CH + AT thin-slice execution](ch-at-thin-slice-execution.md)
- [CH Fedlex fast-loop backlog](ch-fedlex-fast-loop-backlog.md)
- [Five-country acceptance A (CH + AT)](five-country-acceptance-a.md)

## Current posture

What is already strong:

- CH fast-loop path is proven for:
  - narrow law slice
  - second narrow law slice
  - tiny widened batch
- AT fast-loop path is proven for:
  - narrow RIS slice
  - tiny widened RIS batch
- the targeted build/deploy loops now reduce iteration time from release-scale waits to
  service-scoped feedback
- DI + lifecycle are proven on both CH and AT

What still costs too much:

- operators still need too much environment and ID knowledge
- worker/API parity can drift unless explicitly checked
- transport success and content quality are still separate judgments
- evidence capture is improved but still partially manual
- AI is not yet used as a structured reviewer for quality and drift

## Friction categories

We sort friction into four buckets:

1. human-use friction
2. automation and reliability friction
3. quality friction
4. AI acceleration opportunities

Each item below is tagged with one or more of:

- `remove` — simplify or eliminate operator work
- `automate` — codify in scripts/workflows
- `gate` — fail fast when an invariant breaks
- `augment-with-ai` — use AI to speed review or narrowing, not to replace canonical truth

## 1. Human-use friction

### H1. Environment and identity drift

Symptoms:

- operators must remember live IDs like `auth_ris` vs repo seed names such as `auth_at_ris`
- success can depend on runtime-specific naming or env wiring not visible from the happy path
- worker/API drift is discoverable only after a failed run unless explicitly checked

Impact:

- wasted reruns
- false debugging of provider logic
- slow onboarding for anyone who did not watch the recent incidents

Recommended action:

- `remove`: prefer runtime auto-resolution for authority IDs where the live service is the
  canonical source
- `gate`: require API/worker env parity checks in deploy workflows
- `automate`: print resolved authority and jurisdiction IDs in every fast-loop summary

### H2. Too many operator steps still require memory

Symptoms:

- auth bootstrap, deploy choice, run creation, polling, and evidence capture are still separate
  mental steps
- some fixes are obvious only after reading multiple runbooks together

Impact:

- friction for occasional operators
- higher chance of skipping an evidence or validation step

Recommended action:

- `remove`: continue collapsing flows into one-command operator loops
- `automate`: emit ready-to-paste evidence blocks directly from the loop
- `automate`: keep “one service, one deploy, one run, one verdict” as the default pattern

### H3. Failures are not always operator-clear

Symptoms:

- `downstream_failed` is technically correct but does not identify the real break
- some errors still require log spelunking to map to the next action

Impact:

- slower recovery
- more dependence on repo experts

Recommended action:

- `remove`: improve operator verdict taxonomy
- `automate`: map common failure signatures to likely root cause plus next action
- `gate`: distinguish provider failure, handoff failure, and quality failure explicitly

### H4. GA coordination still requires human synthesis

Symptoms:

- the GA board points to the right lanes, but a release owner still has to correlate lane freshness,
  last passing evidence, and current blockers by hand

Impact:

- slower sign-off
- higher risk of “everything looks close” without one crisp next action

Recommended action:

- `automate`: add a machine-readable GA status rollup with:
  - lane freshness
  - last passing evidence
  - open blocker
  - next operator action

## 2. Automation and Reliability friction

### A1. Worker/API parity drift

Symptoms:

- API can be correctly configured for GCS + Pub/Sub while worker is not
- async provider runs then publish bundle manifests DI cannot read

Impact:

- cross-service failures that look like provider or DI regressions

Recommended action:

- `gate`: keep parity checks in deploy workflows
- `automate`: keep worker env vars in env examples and runtime Terraform as first-class config
- `automate`: add a post-deploy smoke that verifies worker artifact storage is not `file://`

### A2. Fast deploy is better, but full runtime deploy is still too coupled

Symptoms:

- unrelated images can still stall broader runtime deploy workflows
- targeted provider work can be blocked by frontend or document-service queue state

Impact:

- unnecessary latency
- deployment risk that is orthogonal to the provider being iterated

Recommended action:

- `remove`: use service-scoped deploy paths for provider iteration by default
- `automate`: keep `platform-control-only` image and deploy workflows as the normal fast path
- `gate`: fail fast if required branch images are missing instead of waiting behind unrelated lanes

### A3. Evidence generation is still post-hoc

Symptoms:

- evidence notes are still authored after a successful run instead of being emitted from the loop
- run IDs, revisions, and downstream records are available but not packaged automatically

Impact:

- duplicated operator effort
- slower ticket updates

Recommended action:

- `automate`: emit a markdown evidence block next to the JSON summary in each fast-loop run dir
- `automate`: generate a `TAR-239` / `TAR-160` paste block automatically from the loop outputs

### A4. Post-deploy checks are still too shallow

Symptoms:

- health and readiness prove service reachability
- they do not prove that a newly deployed provider path can create a run, publish artifacts, and
  receive DI/lifecycle callbacks

Impact:

- green deploys can still hide broken acquisition or handoff behavior

Recommended action:

- `gate`: add an optional post-deploy canary that runs the narrow fast loop and fails the deploy
  for `provider_failed` or `downstream_failed`

### A5. Runner and build reliability remain background risk

Symptoms:

- runner label drift and image-build queueing still exist
- a successful fast path can still be interrupted by image infrastructure issues

Impact:

- hidden latency
- occasional reversion to manual deploy workarounds

Recommended action:

- `gate`: runner preflight should explicitly cover buildx and Artifact Registry reachability
- `automate`: keep image/deploy paths narrow when iterating on a single runtime service
- `remove`: avoid making provider validation depend on the whole runtime image set

## 3. Quality friction

### Q1. Pipeline success is not the same as content success

Symptoms:

- CH initially captured a homepage shell
- CH SPARQL initially captured metadata-only JSON
- AT acquisition can complete while still requiring a content usefulness judgment

Impact:

- false confidence if we look only at run completion
- widening too early

Recommended action:

- `gate`: keep transport checks separate from content checks
- `gate`: require a final verdict such as `pass`, `pipeline_pass_content_suspect`,
  `provider_failed`, or `downstream_failed`

### Q2. Current content checks are still thin

Symptoms:

- title and section checks are useful but shallow
- we do not yet score document cleanliness, boilerplate ratio, or wrong-manifestation risk

Impact:

- quality regressions can sneak through a technically green loop

Recommended action:

- `gate`: add document-shape checks such as:
  - expected legal title family
  - expected article/section density
  - expected final URL pattern
  - language agreement
- `augment-with-ai`: classify captured outputs into:
  - likely_good
  - boilerplate
  - wrong_document
  - incomplete
  - needs_operator_review

### Q3. Promotion logic still depends on operator judgment alone

Symptoms:

- widening decisions are still mostly manual
- run-to-run comparisons are not synthesized automatically

Impact:

- slower confident iteration
- harder autonomous improvement

Recommended action:

- `automate`: compare each run to the last accepted run on:
  - capture count
  - content types
  - downstream status completeness
  - quality classification summary
- `augment-with-ai`: generate “improved / unchanged / regressed” judgments with short rationale

## 4. AI acceleration opportunities

### AI should help as reviewer and narrowing assistant, not as canonical authority

Safe AI uses:

- summarize captured artifacts and run deltas
- classify quality problems
- suggest tighter seed URLs, include/exclude rules, or language constraints
- cluster discovered pages by type and authority hints
- generate evidence summaries for tickets and runbooks

Unsafe AI uses:

- invent canonical jurisdiction or authority IDs
- become the final source of truth for production mappings
- replace deterministic provider logic for official corpora
- auto-promote a source version without a deterministic evidence path

### Best near-term AI tasks

1. post-run quality reviewer
   - inputs: raw artifacts, preview summary, captured resources
   - outputs: quality class, likely issues, widening recommendation

2. run delta summarizer
   - inputs: current run bundle + previous accepted run bundle
   - outputs: what improved, what regressed, what to inspect next

3. discovery assistant for exploratory slices
   - inputs: bounded crawl or captured sample set
   - outputs: candidate stable paths, candidate authority buckets, likely include/exclude rules

4. evidence pack drafter
   - inputs: fast-loop summary JSON and run metadata
   - outputs: `TAR-239` / `TAR-160` paste blocks and operator notes

## Prioritized action backlog

### P0 - do next

1. Auto-generate markdown evidence next to the JSON summary for both CH and AT fast loops.
   Tags: `automate`, `remove`

2. Add a post-deploy smoke that checks worker artifact storage and bundle publication are
   configured for cross-service DI.
   Tags: `gate`, `automate`

3. Add a run-to-run comparison summary for fast loops.
   Tags: `automate`, `augment-with-ai`

4. Add a machine-readable GA status rollup with one `next operator action` per lane.
   Tags: `automate`, `remove`

### P1 - do soon

5. Add stronger content-quality gates:
   - language agreement
   - URL pattern agreement
   - structure density heuristics
   Tags: `gate`

6. Add an AI reviewer that classifies each captured artifact set as likely usable or suspect.
   Tags: `augment-with-ai`

7. Generate ready-to-paste Linear summary blocks from successful fast-loop runs.
   Tags: `automate`, `remove`

8. Add a post-deploy end-to-end canary step to the narrow deploy path.
   Tags: `gate`, `automate`

### P2 - after the loop is stable

9. Use Temporal above the deterministic providers for:
   - shard scheduling
   - retries
   - backfills
   - checkpointing
   Tags: `automate`

10. Add broader exploratory AI-assisted discovery only for new corpora or poorly structured portals.
   Tags: `augment-with-ai`

## Suggested parallel worker lanes

These are good next delegated lanes once this map is accepted:

### Lane 1 - evidence automation

- extend CH and AT fast-loop scripts to emit markdown evidence automatically
- include ticket-ready summary blocks

### Lane 2 - quality scoring

- add structural content checks and a run comparison summary
- define a stable verdict model that separates transport from content usefulness

### Lane 3 - AI review assistant

- prototype a post-run reviewer that classifies artifact quality and suggests widening or tightening

### Lane 4 - deploy/reliability hardening

- ensure worker/API parity is enforced in all runtime deploy paths
- add a focused smoke for bundle-manifest storage readability

### Lane 5 - GA rollup automation

- produce a machine-readable lane summary for GA
- show freshness, blocker, and next action without requiring cross-doc synthesis

## Decision rule

For the next phase, prefer:

1. deterministic provider truth
2. automated deploy/run/evidence loops
3. explicit quality gates
4. AI review layered on top

Do not reverse that order.
