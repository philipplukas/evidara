# ADR-0040: What Makes a Test Result Trustworthy

## Status

Proposed

## Date

2026-07-19

## Context

On 2026-07-19 a single day's work turned up more than a dozen distinct ways this
repo's test suite reported green while proving nothing. They were not one bug.
They were three different mechanisms, each of which independently converts "I do
not know" into "pass".

This is an architectural decision, not a testing-hygiene note, because it
changes **what counts as evidence**. Every gate in `AGENTS.md`, every "narrowest
test that proves the change" in the PR checklist, and every merge decision rests
on the assumption that a green run is information. Where that assumption is
false, the entire review process is running open-loop, and no amount of care in
individual PRs recovers it.

### A. Isolation — a run can touch state outside itself

Playwright's `reuseExistingServer` reuses whatever is already listening on the
port. It does not check that the listener is the app under test. This hit four
lanes on the same day:

- One lane's Playwright run attached to **another lane's dev server** and
  reported green over code it did not have checked out.
- One lane bound to a **stale Docker container** and reported the exact bug it
  had just fixed — a red run that was evidence about a container image, not
  about the diff.
- A docker helper script running as **root** left root-owned artifacts in the
  working tree; subsequent runs died on `EACCES`, and the first instinct was to
  suspect the tests.
- A repo-root `node_modules` **symlink** let module resolution escape a git
  worktree entirely, so a worktree's tests resolved a sibling checkout's
  dependencies (#588 — the case `scripts/check-js-workspace-hygiene.sh` guards).

The common shape: the run's result depended on ambient state that no one
declared, that the report does not mention, and that differs between the
developer's machine and CI.

### B. Coverage honesty — what CI runs differs from what the suite appears to contain

The file tree is not the test plan. What CI invokes is.

- `legal-search/frontend` has seven Playwright specs. CI selects them four ways:
  three tag filters (`-g @smoke`, `-g @contract`, `-g @screenshots`) and one
  command that names **a single file by path** (`e2e:visual`). Any spec that is
  neither tagged nor that file is invisible.
- `e2e/workspace-panels.spec.ts` carries no tag at all. It sat 4-of-6 red on
  `main` and nobody noticed, because nothing ran it. The panel-geometry guard
  #605 added has been inert since the day it landed — a test written
  *specifically to catch a regression* that could not have caught it.
- `platform-control/admin` has five Playwright specs, an `e2e` script that runs
  them, and no workflow that calls it. `npm run lint` covers `e2e/`, so they are
  formatted, typechecked, and never executed.
- 15 DSPy tests sit behind an uninstalled extra, under a comment claiming they
  run in CI. Module-level `pytest.importorskip` deletes whole files from a run
  with no signal above "collected fewer items".
- `document-intelligence` had no row in the `CLAUDE.md` gate table, so the
  obvious local command (`uv run pytest`) under-collected relative to CI and
  reported green over a smaller suite (fixed in #664).

The common shape: a plausible-looking count of passing tests, over a population
nobody had measured.

### C. Assertion strength — what runs does not assert enough

- `maxDiffPixelRatio: 0.06` set at the Playwright **project** level applied to
  every screenshot in the suite. At the sizes involved it tolerated roughly a
  260px layout error, which it duly swallowed for three months.
- Some visual baselines were blessed **inside a bug window**. A baseline is a
  photograph of whatever was on screen when someone ran `--update-snapshots`; if
  the bug was on screen, the baseline now asserts the bug and fails on the fix.
- `expect(x).toBeGreaterThanOrEqual(1)` where `toHaveLength(1)` was meant. A
  duplicate-count bug produced 2 and passed.
- A hygiene guard used `grep -rl … | grep -qv node_modules`. On empty input
  `grep -qv` exits 0 under some implementations and 1 under GNU grep, so the
  guard fired precisely when the violation was **absent** — it reported a
  Dockerfile that does not exist (fixed in #702).

The common shape: an assertion whose passing condition is much weaker than the
property the author believed they were checking.

### The ordering matters

These three are not a checklist to work through in parallel. They compose in one
direction only:

> **A before B before C.**

A tolerance argument is meaningless if the run might not be hitting your code at
all. Knowing exactly which specs run is meaningless if what runs asserts nothing.
Spending a day tightening `maxDiffPixelRatio` while `reuseExistingServer` can
still bind a foreign server is not 30% of the fix — it is zero, plus a false
sense that the area has been handled.

### The uncomfortable part

This project exists because a legal-research system that answers "probably
Article 12" when it does not know is worse than one that refuses. ADR-0033 makes
refusal a first-class outcome; the acceptance test is explicitly satisfied by a
**correct refusal**.

This ADR's own number is an instance. It was first written as 0038, because
0037 was the highest on `main` and the next integer was therefore "free". Two
other in-flight lanes reasoned identically and had already taken 0038 and 0039.
Three lanes each substituted a plausible number for a verified one, and git
would have merged all three without a conflict — the files have different
names. Hence `scripts/check_adr_numbers.py`, and hence this paragraph, which is
cheaper than the next collision.

Every failure above is that same substitution, one level up: a test harness that
does not know whether the code works, emitting "pass". A skipped test that
reports green, an untagged spec that inflates an apparent suite, a 6% pixel
tolerance — each is a plausible value standing in for an absent one. We are
building a machine to refuse to guess, using tooling that guesses.

## Decision

**A test result is trustworthy only when all three hold, checked in this order:**

1. **Isolation** — the run's inputs are determined by the checkout under test.
   No ambient server, container, port, filesystem artifact, or module-resolution
   path may influence the outcome without being declared. Where reuse is
   allowed, the runner must verify *identity*, not merely *liveness*.
2. **Coverage honesty** — every committed test file is collectable by some CI
   job, every skip is argued for, and the local gate collects the same
   population as CI. A test that cannot run is not coverage; it is the
   appearance of coverage, which is worse, because it stops anyone from looking.
3. **Assertion strength** — the assertion's passing condition matches the
   property being claimed. Tolerances are set at the narrowest scope that needs
   them and justified where they are set; baselines record a state someone
   verified, not merely a state that occurred.

**Corollaries that follow from the ordering:**

- Work on C is not accepted while a known A-class defect is open on the same
  surface. The C fix cannot be validated by the very runs A has compromised.
- "The suite is green" is not an argument in review. "This job ran this spec and
  it asserted this property" is.
- Every guard added under this ADR must be **self-tested in both directions** —
  it must be shown to fire on a violation *and* stay quiet without one. #702's
  inverted `grep -qv` passed review because nobody asked it to fail. A guard
  that has only been observed passing is indistinguishable from a guard that
  cannot fail.
- Prefer checking **outcomes over syntax**. `scripts/ci_skip_guard.py`
  observes that a test was skipped rather than grepping for `importorskip`,
  because a grep sees one spelling and misses a runtime `pytest.skip()` inside
  an `except OSError`.
- Debt is **registered, not silenced**. Where a violation is knowingly left in
  place, it goes in a named register with a reason that is printed on every run,
  and a stale entry fails the build. Registers used this way:
  `ALLOWED_SKIPS` (per suite, wired to `scripts/ci_skip_guard.py`), `KNOWN_UNREACHABLE`
  (`scripts/check_test_reachability.py`).

## Status of the work

**Landed:**

| What | Where |
|---|---|
| `document-intelligence` gate row, so the local command collects what CI collects | #664 (`CLAUDE.md` per-surface gate table) |
| Silent skips catalogued across the suite | #698 |
| Inverted `grep -qv` guard rewritten, with a fixture-tree self-test asserting both directions | #702 (`scripts/check-js-workspace-hygiene.sh`, `scripts/tests/test_check_js_workspace_hygiene.py`) |
| "CI may not skip" generalised from the #564 Temporal site to the whole platform-control suite | #704 (then `platform-control/tests/ci_skip_guard.py`; moved to `scripts/` by #690) |
| The same guard adopted as a repo convention — shared by platform-control, document-intelligence and eval, and extended to catch whole modules dropped at collection | #690 (`scripts/ci_skip_guard.py`) |
| DSPy tests over the production LLM extractor made to actually run, via the `llm` extra in CI | #685 (`scripts/check-document-intelligence.sh`) |
| Visual baselines re-blessed outside the bug window | #700 |
| Reachability check — enumerates specs, enumerates what CI invokes, fails on any spec no job can reach | #686 (`scripts/check_test_reachability.py`) |
| ADR number-collision guard — two files may not claim one number | #686 (`scripts/check_adr_numbers.py`) |

**In flight:**

- **Isolation lane** — `reuseExistingServer`, port allocation, and the docker
  helper script. Owns everything in section A. This ADR describes the principle;
  that lane implements it.
- **#611** — VRT tolerance scoping and baseline provenance. Owns section C's
  first two items.

**Remaining, unowned:**

- 12 test files are reachable by no CI job. They are registered in
  `KNOWN_UNREACHABLE` with reasons and are visible on every run, but registering
  debt is not paying it. The largest single item is the five
  `platform-control/admin` Playwright specs, which need a job, not a tag.
- **No JS equivalent of `ci_skip_guard.py`.** The reachability check is
  file-level, so a collected file may still contain a test that never runs:
  `e2e/smoke.spec.ts` guards its only real-backend test with
  `test.skip(!USE_REAL_BACKEND, ...)` and no job sets that variable (#686
  case 3). Python fails the run on an unargued skip; vitest and Playwright do
  not. This is the largest open B-class gap.
- No guard exists for section C in general. Assertion strength is currently
  enforced by review alone, and review is exactly what missed
  `toBeGreaterThanOrEqual(1)`. A mutation-testing spike on the narrowest
  high-value surface is the obvious probe; nothing is scheduled.
- The local-versus-CI population gap is closed by convention (the `CLAUDE.md`
  gate table) rather than by a check. The gate table is hand-maintained, which
  is the failure mode ADR-0034 documents for hand-maintained artifacts.

## Consequences

### Positive

- A green run means something specific, and the meaning is checkable.
- The three causes give review a vocabulary. "This is an A problem" is more
  actionable than "the tests are flaky".
- The ordering prevents the most common wasted effort in this area: tuning
  assertions on a harness that is not reliably running the code.
- Debt registers make the size of the problem a number on every CI run rather
  than a thing people rediscover.

### Negative

- More gates that can block a PR, including on days when the underlying test
  change is trivial. This is the intended trade.
- Registering debt is a legitimate escape hatch and can be abused. The
  mitigation is that entries are printed, require a reason, and go stale loudly
  — not that they are hard to add.
- The reachability check parses workflows, shell scripts, and `package.json`
  indirection without a full shell or YAML interpreter. It can be defeated by
  sufficiently dynamic invocation. It fails loudly if it parses zero
  invocations, but a partially-broken parser would under-report.

### Neutral

- `docs/testing/testing-principles.md` and `docs/testing/ci-testing-strategy.md`
  gain a "trust" section pointing here. Those documents describe what to test
  and when; this one describes when to believe the answer.

## Alternatives considered

**Treat these as unrelated bugs and fix each in place.** This is what happened
before today, repeatedly. #564 fixed one skip site; #690 found the same shape at
three others. Point fixes do not generalise because the problem is a default
(absence reads as success), not a set of sites.

**Require 100% of tests to run in CI, no register.** Cleaner in principle, and it
would have forced the admin Playwright job to exist. Rejected because the honest
current count is 12 and the fix for several of them is a new CI job with
infrastructure implications. A check that cannot go green on `main` gets
disabled within a week, which converts a measured problem back into an
unmeasured one.

**Rely on coverage percentage.** Line coverage is orthogonal to all three causes.
A suite bound to a stale container reports high coverage of the wrong binary.

## References

- ADR-0033 — agentic legal reasoning; the refusal-over-plausible-answer principle
  this ADR applies to tooling
- ADR-0034 — hand-maintained artifacts drift; the same argument for contracts
- `scripts/ci_skip_guard.py` — outcome-over-syntax guard, shared by every Python suite
- `scripts/check-js-workspace-hygiene.sh` — both-directions self-test, prior art
- `scripts/check_test_reachability.py` — the coverage-honesty check this ADR ships with
- Issues: #564, #588, #605, #611, #646, #664, #686, #688, #690, #698, #700, #702, #704
