@AGENTS.md

## Claude Code quick reference

Repo-wide conventions live in `AGENTS.md` (imported above). This file only adds Claude-Code-specific pointers not covered there.

### Planning anchor

**#628 (M13) closed 2026-07-19.** Its successor is **#958**, below. Do not scope work against #628
— read its closing comments for what iterations 1 and 2 measured, then work #958 and the live issues
it names.

The programme is unchanged and still executes
[ADR-0033](docs/adr/0033-agentic-legal-reasoning.md) (Accepted): the bet is that a thorough data
platform for law makes AI use cases easy, so the deliverable is the **loop** — blueprint → source
version → acceptance run → evidence → `enabled: true` → approval — not the corpus, which is its
output. The vertical slice is iteration 1; breadth is iterations 2..N.

Acceptance test: ADR-0033's dog question, answered over a corpus **assembled through the platform**
— or refused correctly because the ordinance is not in it.

ADR-0033 §4 is a standing guardrail: **do not build the MCP server first.** Its build order is
dependency-forced; #628's closing comments track which steps were done.

**Current anchor: #958 — the corpus states what is true, or refuses.** Opened 2026-09-09 as the
successor to both closed anchors below.

The milestone is the **refusal half** of the acceptance test above, which has had almost no
attention: answering the dog question is one passing answer, and refusing correctly for a norm the
corpus does not hold is the other. We cannot currently do the second, because five open issues share
one defect — nothing in the stack reliably distinguishes *absent* from *broken*: #850 (a new
`document_id` per version), #806 (a known-wrong record in the production index), #871 (metadata keys
silently dropped), #891 (sparse retrieval returning the whole index when BM25 abstains), #953 (a 500
rendered as "no version"). That is ADR-0052's *unknown ≠ zero* promoted from a per-screen discipline
to a system property. #958 carries the build order.

**Where agents fit, because it is easy to get backwards.** ADR-0022 already decided it:
`tools/evidara-cli` is the bounded surface agents act through, `platform-control` is the durable
system of record for runs, step history and approvals. **Agents do not get a UI.** The admin panel is
the evidence-and-approval surface — where a human sees what an agent did, on what basis, and grants
or withholds permission. That surface is currently the weakest part of the panel (#949: the approval
screen can neither approve nor show its evidence), which makes it milestone work, not polish.

ADR-0022 is partially built: the `workflow` verb tree exists in the CLI and
`WizardRunLedger.state_transitions` is the journal, but the ADR's `inspect`/`propose`/`apply`/
`verify`/`compensate` family exists only as `proposal.py:46`. Finish it rather than re-litigate it.

**Two closed anchors, kept because their evidence is still load-bearing:**

- **#731 — the LexFind provider** (26 cantons + Bund behind one unauthenticated JSON API), closed
  COMPLETED 2026-09-03. It landed the cantonal rung of the dog question — `tol/22871` is the ZH
  Hundegesetz, md5-identical to the canton's own PDF — and its `version_inactive_since` field models
  repeal separately from consolidation date, which is what the #661 trap needed.
- It was prioritised above the municipal rung (#736, #584) on measured evidence, not preference: the
  2026-07-22 full survey of all 2,110 Swiss communes found platform clustering covers only ~5% of the
  registry, and that share did not improve as coverage went from 61% to 100%. #736's premise — that
  clustering turns ~2,110 units into ~15 — is **still** not supported, and those two stay parked
  until #958's steps 3–5 are done. Breadth is cheap now and expensive to trust.

**This pointer has gone stale twice** — it named #628 for three days after it closed, then #731 for
six days after that. If you are briefed from an anchor, check its state before scoping against it.

That paragraph was here for both of those, which is the evidence that writing it down does not
maintain it. `scripts/check_planning_anchor.py` now reads the `**Current anchor: #N` line above,
resolves the issue's state, and fails the `docs-lint` job when it is CLOSED. It runs in CI and in
`scripts/check_docs.sh`; with no `gh` and no token it reports `DID-NOT-RUN` rather than passing.

The predecessor M1–M6 roadmap (#279) closed 2026-04-20. When opening new work, prefer
`/issue-execute <number>` if a ticket exists; otherwise scope inline against ADR-0033's build order.

### Per-surface quality gates

Run the narrowest gate for the surface you touched before pushing, **through
`scripts/run-gate.sh`**:

```bash
bash scripts/run-gate.sh <name> [--dir <surface>] -- <command...>
```

It runs the command under `set -o pipefail`, tees the full output to a log, and
prints a final line that is exactly one of `PASS`, `FAIL` or `DID-NOT-RUN` plus
the command's own exit status and the log path. **Read that line, not the
shell's `$?`.** On 2026-09-19 a gate was run as `... | tail -40`; the suite
failed, `tail` exited 0, and the run was recorded green. That is not an unusual
mistake — a pipeline's status is its *last* command's, so every `| tail`,
`| head` and `| grep` launders a failure into a success, and it happened
repeatedly in one session before anyone caught it. `DID-NOT-RUN` exits 2 and is
never 0: a gate whose prerequisites were absent did not pass.

| Surface | Gate |
|---|---|
| `platform-control/` | `bash scripts/run-gate.sh platform-control -- bash scripts/check-platform-control.sh` — ruff check + ruff format --check + pytest **and** the OpenAPI contract-drift gate **and** the full admin gate. A bare `uv run pytest` is narrower than CI. |
| `platform-control/admin/` | `bash scripts/run-gate.sh admin --dir platform-control/admin -- npm run check`, then the same with `-- npm run build` |
| `document-intelligence/` | `CI=true bash scripts/run-gate.sh document-intelligence --dir document-intelligence -- uv run --extra dev --extra service --extra test --extra llm pytest`, then `-- uv run ruff check .` and `-- uv run ruff format --check .` — `CI=true` is not optional, see below |
| `legal-search/api/` | `bash scripts/run-gate.sh legal-search-api --dir legal-search/api -- npm run check` — includes the injection-token audit (`src/core/di/injection-token-providers.spec.ts`), which fails on a token nothing `provide:`s |
| `legal-search/frontend/` | `bash scripts/run-gate.sh legal-search-frontend --dir legal-search/frontend -- npm run check`, then the same with `-- npm run build` — build is a separate CI step; it catches SSR issues `tsc` misses |
| `legal-search/` (both surfaces) | `bash scripts/run-gate.sh legal-search -- bash scripts/check-legal-search.sh` |
| `legal-search/frontend/e2e/` or `platform-control/admin/e2e/` | `bash scripts/run-gate.sh e2e-coverage -- bash scripts/check-e2e-spec-coverage.sh` — asserts every spec is selected by some CI command (#686). It skips a surface whose `node_modules` is absent, so run `npm ci` in the surface you touched first or the check passes having checked nothing. |
| `CLAUDE.md`, `AGENTS.md`, `.github/ISSUE_TEMPLATE/`, `.claude/commands/issue-execute.md`, `docs/process/` run each of `scripts/check_planning_anchor.py`, `scripts/check_classifier_evidence_rule.py`, `scripts/check_measured_premise.py` and `scripts/check_api_version_lane.py` through `bash scripts/run-gate.sh <name> -- python3 <script>` — the four pointer checks in the `docs-lint` job. The anchor check reports `DID-NOT-RUN` without `gh` or a `GH_TOKEN`; `--require-network` turns that into a failure. |
| `platform-control/admin/e2e/` | `bash scripts/run-gate.sh admin-e2e --dir platform-control/admin -- npm run e2e:browsers`, then `-- npm run e2e` and `-- npm run e2e:visual` — the admin's Playwright suite. Every spec mocks the API with `page.route`, so no backend is needed. It is the only layer that sees layout, stylesheets and routing: jsdom has none of the three, which is how a clipped ACTIONS column, a UA-beveled sort header and an absent dark mode all passed `npm run check`. `npm run e2e` runs `--grep-invert @visual`, so **`e2e:visual` is a separate command and a separate CI job** — running only the first is narrower than CI. Its pixel baseline lives in this surface as of #913 (a PNG has no merge strategy, and an admin change was failing a *legal-search* job — #895, #902, #905); regenerate it with the `visual-baseline-refresh` PR label, not locally. Both commands need a free port: `ADMIN_E2E_PORT=3010`. |
| `marketing/` | `bash scripts/run-gate.sh marketing --dir marketing -- npm run check`, then the same with `-- npm run build` — the static export is the deploy artifact |
| `tools/evidara-cli/` | `bash scripts/run-gate.sh evidara-cli -- bash scripts/check-evidara-cli.sh` |
| `eval/` | see `.github/workflows/eval-ris.yml` — two `-k`-filtered pytest selections |
| `scripts/` | `bash scripts/run-gate.sh scripts -- uv run --with pyyaml python -m unittest discover -s scripts/tests -p "test_*.py"` — see note below; without pyyaml only 264 of 404 tests run (measured 2026-09-19) |
| `country-overlays/` or `platform-control/src/platform_control/seeds/` | `for c in AT CH DE FR IT EU; do bash scripts/run-gate.sh "overlay-$c" -- python3 scripts/check_country_overlay_files.py --country "$c"; done` — `--country` is required; the bare command exits 2 on argparse |
| `contracts/api/` or `contracts/events/` | `bash scripts/run-gate.sh contract-changeset -- python3 scripts/check_contract_version_bump.py --base origin/main` — the contract **changeset** gate. **Not** covered by `check-platform-control.sh`, which only checks that the generated spec still matches the app. |
| `infra/hetzner/` | `bash scripts/run-gate.sh hetzner-ownership -- python3 scripts/check_platform_ownership.py` — the shared cluster layer moved to [`research-platform`](https://github.com/philipplukas/research-platform) and the copies here are **frozen by hash**. An edit to a frozen file does not reach the cluster; the guard refuses it and names where the change belongs. Also run `scripts/validate_hetzner_apps_kustomize.sh` and `scripts/check_hetzner_image_pins.py` through the wrapper — the two that cover what this repo still owns. |
| Any scraping-touching PR | `bash scripts/run-gate.sh scraping-qa -- bash scripts/check-scraping-qa.sh` |

Rows here must not be narrower than what CI runs: a clean local run against a
narrower gate means nothing, and the gap surfaces as a surprise red (#664, #688).

The wrapper does not make a gate correct — it makes its *outcome* readable. It
detects the prerequisites this repo has actually been burned by (no Docker
daemon for a Testcontainers layer, an `npm` gate in a tree with no
`node_modules`, a command that is not on `PATH`) and reports `DID-NOT-RUN` for
those; anything it cannot detect is left to the command, because a wrapper that
guesses wrong in the other direction is no better than one that prints PASS.
State `--requires docker`, `--requires path:…`, `--requires cmd:…` or
`--requires env:…` when you know a prerequisite it cannot infer.

For `scripts/`, `--with pyyaml` is not optional either. CI installs it via
`requirements-docs.txt`; a workstation `python3` may or may not have it, and that is the
point — the gate must not depend on ambient state. Measured again on 2026-09-19: without it
the runner reports `Ran 264 tests ... FAILED (failures=5, errors=15)` against 404 with it —
which reads as twenty broken tests and is really **a hundred and forty that never ran**.
`uv` is already required by this repo, so the command above needs no venv and no system
package.

`infra/hetzner/` is a trap of its own kind, and the opposite one: the guard exists and
is correct, but a **frozen file is not obviously frozen from the file itself**. Nothing
in `infra/hetzner/values/minio.yaml` says another repo owns it — you find out from the
guard, or from `infra/hetzner/OWNERSHIP.md`, or not at all. Verified 2026-09-08:
tampering with that file fails the check, restoring it passes, and editing
`infra/hetzner/apps/kustomization.yaml` is correctly permitted because `apps/` stayed.

The `contracts/` row above is the same trap in a second place: `check_contract_version_bump.py`
fires on any change under `contracts/api/` or `contracts/events/` (`:42`) and is run by no surface
script. Two PRs from one lane hit it in a single day (2026-09-03) because the `platform-control/`
row reads as exhaustive and is not.

**What it requires changed on 2026-09-09 (#913).** It used to demand a hand-edit of
`contracts/manifest.yaml`'s **top-level `version`**, which serialised every contract PR on one
scalar. It now demands a **changeset** under `contracts/changes/` —
`python3 scripts/bump_contract_version.py --minor --summary "..."`, plus `--api` when the
platform-control surface changed. Two PRs write two different files, so neither the textual conflict
(different successors) nor the semantic one (the same successor, which merges cleanly and then failed
the old tip-of-main comparison) can happen. The number is computed once, at release, by
`scripts/release_contract_version.py --check` / (no flag) — the **only** writer of that key; a test
in `scripts/tests/test_contract_changesets.py` fails if a second script grows one.
`apis.platform_control.version` is unaffected and still moves in the PR:
`check_contract_manifest.py` requires it to equal the generated spec's `info.version`, so it is
pinned to the app.

**`CI=true` is not optional either, on any suite that registers the CI-skip guard** —
`document-intelligence/tests/conftest.py`, `platform-control/tests/conftest.py` and
`eval/conftest.py` all do. The guard (#690, `scripts/ci_skip_guard.py`) fails the run when a test
skips in CI for a reason that is not in that suite's `ALLOWED_SKIPS`. Its trigger is
`running_in_ci()`, which is `bool(os.environ.get("CI"))` (`scripts/ci_skip_guard.py:61-63`) — so a
workstation shell **can never fire it**, and a whole class of CI failure is invisible locally no
matter which extras you pass. Neither `scripts/check-platform-control.sh` nor
`scripts/check-document-intelligence.sh` sets `CI`, so prefix it yourself. Adding a test that skips
without an allowlist entry is green locally and red in CI (observed on #840, 2026-09-03).

For `document-intelligence/`, the extras are not optional: a bare `uv run pytest` cannot collect
`test_instructor_extractor` or `test_eval_docling_extractor` and reports green over a smaller suite
than CI runs. `--extra llm` is on that list as of #685 — without it `test_dspy_modules.py` (11 tests)
is dropped at collection and `test_eval_dspy_extraction.py::test_eval_harness_runs_mock` skips,
covering the production LLM metadata extractor with nothing. `ruff format --check` is likewise part
of the CI job, not just `ruff check`. The full
CI gate is `scripts/check-document-intelligence.sh`, but it installs into the ambient `python3`
rather than a uv environment, so prefer the command above locally.

**Which dependency set each gate runs, and why they differ (#848).** There are two, deliberately:

| Runs | Dependency set | Python |
|---|---|---|
| The command above (`uv run`) | `uv.lock` | `document-intelligence/.python-version` (3.12) |
| `document-intelligence-locked` CI job | `uv.lock` (`uv sync --frozen`) | 3.12 |
| `document-intelligence/Dockerfile*` | `uv.lock` (`uv sync --frozen`) | 3.12 (base image) |
| `document-intelligence-check` CI job + `scripts/check-document-intelligence.sh` | `pyproject.toml` **floors**, resolved against PyPI on the day | 3.12 |

The locked row is what ships; the floating row is the early warning that a new
`deltalake`/`pyarrow` broke us. Until #848 the image also floated and the local gate was the
only locked runner, so the two silently disagreed — measured 2026-09-03, the image built
`deltalake` 1.6.3 / `pyarrow` 25.0.1 while `uv run` gave 1.5.0 / 23.0.1 on Python **3.13**.
Bumping a floor without re-locking now fails `uv sync --frozen` in CI and in the image build
rather than shipping something no gate ran.

### ID contract (see #264)

Canonical seeds: `platform-control/src/platform_control/seeds/reference/{authorities,jurisdictions,compliance_policies,extractor_profiles}.yaml`.
Legacy (being retired): `platform-control/src/platform_control/hierarchies/{authorities,jurisdictions}.yaml`.
Any PR that renames or adds an `authority_id` / `jurisdiction_id` must keep the canary script `scripts/ch-fedlex-fast-loop.sh` functional — it hardcodes `auth_fedlex` and `jur_ch_federal`.

### Alembic

Migrations under `platform-control/`. Current head at time of M0: `20260417_0010` (see #253 for staging/prod rollout).

### ADRs

`docs/adr/` — numbered. Add one for any architecture-level decision (see AGENTS.md rule on `architecture-change`).
