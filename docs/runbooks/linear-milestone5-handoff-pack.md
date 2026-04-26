# Linear handoff pack — M5 through Phase 5 completion

Owner: Platform / release  
Last reviewed: 2026-04-12  
Last verified: 2026-04-12  
Applies to: closing **M5 evidence** (TAR-64 / TAR-77 / TAR-85), **Phase 5** readiness (TAR-69), and follow-on gates through **full product GO** where applicable.

## Linear issues created from this pack (2026-04-12)

These were filed via the **Linear MCP** into team **Tart-baozi**, project **Evidara**, milestone **M5 — Close P5/P6/P7 Open Items**:

| Issue | Role |
|-------|------|
| [TAR-214](https://linear.app/tart-baozi/issue/TAR-214) | Operator — refresh M5 gate evidence (umbrella) |
| [TAR-215](https://linear.app/tart-baozi/issue/TAR-215) | Agent — TAR-89 data path |
| [TAR-216](https://linear.app/tart-baozi/issue/TAR-216) | Agent — TAR-89 serving path |
| [TAR-217](https://linear.app/tart-baozi/issue/TAR-217) | Operator — TAR-89 environment truth |
| [TAR-218](https://linear.app/tart-baozi/issue/TAR-218) | Agent — DI CI/CD bundle + Terraform (Backlog) |
| [TAR-219](https://linear.app/tart-baozi/issue/TAR-219) | Agent — Release Readiness dev-first doc pairing |
| [TAR-220](https://linear.app/tart-baozi/issue/TAR-220) | Operator — TAR-67 drills + artifacts |
| [TAR-221](https://linear.app/tart-baozi/issue/TAR-221) | Operator — TAR-82 / TAR-68 relevance pack |

Comments added on **TAR-69** and **TAR-89** linking the umbrella and child split.

**Repo hygiene:** `scripts/deploy-hetzner-runner.sh` is **gitignored** (operator-local host paths). Keep a personal copy outside the repo if you use it.

## Why this file exists

The monorepo **does not** create Linear issues in CI by default. Operators or agents with the **Linear MCP / CLI** can sync from this document. Use this file to:

1. **Paste** the issue bodies below into Linear (new issues or comments on existing ones).
2. **Assign** work type: **Operator** (GCP/GitHub/console), **Agent-code** (repo PRs), or **Doc** (markdown-only).
3. **Link** child issues under the suggested parents so agents and humans share one backlog.

**Canonical runbooks** (do not duplicate procedure detail here):

- [Phase 5 evidence checklist](phase-5-evidence-checklist.md) — when M5 is “green”
- [M5 evidence checklist](m5-evidence-checklist.md) — operator steps including DI Pub/Sub debugging
- [Phase 5 go / no-go memo](phase-5-go-no-go-memo.md) — gate table + §7 workstreams
- [MVP demo release recommendation](mvp-demo-release-recommendation.md) — evidence packet + full product GO
- [Metadata quality plan status](metadata-quality-plan-status.md) — TAR-89 acceptance pointers
- [TAR-89 workstreams](tar-89-workstreams.md) — data / serving / environment tracks

---

## Suggested Linear hierarchy (minimal)

| Role | Linear | Notes |
|------|--------|--------|
| Parent / decision | [TAR-69](https://linear.app/tart-baozi/issue/TAR-69) | Phase 5 go/no-go owner; summary comment when gates flip |
| M5 gate A | [TAR-77](https://linear.app/tart-baozi/issue/TAR-77) | Branch protection |
| M5 gate B | [TAR-64](https://linear.app/tart-baozi/issue/TAR-64) | Dev e2e ×2 |
| M5 gate C | [TAR-85](https://linear.app/tart-baozi/issue/TAR-85) | Remote MVP acceptance |
| Quality | [TAR-89](https://linear.app/tart-baozi/issue/TAR-89) | Metadata credibility — use **child issues** from [tar-89-workstreams](tar-89-workstreams.md) |
| Relevance | [TAR-82](https://linear.app/tart-baozi/issue/TAR-82), [TAR-68](https://linear.app/tart-baozi/issue/TAR-68) | Baselines (adjacent to M5) |
| Full GO extras | [TAR-87](https://linear.app/tart-baozi/issue/TAR-87), [TAR-88](https://linear.app/tart-baozi/issue/TAR-88) | Walkthrough evidence per [mvp-demo-release-recommendation](mvp-demo-release-recommendation.md) |
| Phase 5 engineering | [TAR-66](https://linear.app/tart-baozi/issue/TAR-66), [TAR-62](https://linear.app/tart-baozi/issue/TAR-62), [TAR-63](https://linear.app/tart-baozi/issue/TAR-63), [TAR-67](https://linear.app/tart-baozi/issue/TAR-67) | Memo §7 |
| Optional | [TAR-139](https://linear.app/tart-baozi/issue/TAR-139) | Agent discovery surface |

---

## Tier A — M5 blocking evidence (defines “M5 green”)

### A1 — Update [TAR-77](https://linear.app/tart-baozi/issue/TAR-77) (branch protection)

**Work type:** Operator (+ repo admin)

**Paste into issue (append to description or first comment):**

```markdown
## M5 handoff — acceptance (TAR-77)

### Goal
`main` cannot merge without the agreed strict quality gate.

### Tasks
- [ ] GitHub → Settings → Branches → `main` protection rule requires **Release Readiness** (or documented equivalent).
- [ ] Capture **screenshot** of the rule showing the required check name.
- [ ] Attach **one green** `Release Readiness` workflow run URL (strict GO).
- [ ] Cross-link: `docs/runbooks/screenshot-evidence-discipline.md`

### Done when
Evidence attached on this issue and linked from TAR-69 / phase-5-go-no-go memo §2.
```

---

### A2 — Update [TAR-64](https://linear.app/tart-baozi/issue/TAR-64) (dev vertical slice ×2)

**Work type:** Operator (primary) + **Agent-code** only if infra/scripts bugs block smoke

**Paste into issue:**

```markdown
## M5 handoff — acceptance (TAR-64)

### Goal
Two successful **dev** vertical-slice smokes on **separate** occasions (different calendar days or different `main` SHAs), each with **Gate D** identifiers (`platform_control_run_id`, `legal_search_document_id`, etc.).

### Prerequisites (before blaming code)
Complete `docs/runbooks/m5-evidence-checklist.md` §TAR-64 — especially **DI Pub/Sub step 7** debugging order:
- Run completed with captures?
- `artifact_bundle.available` subscription push target correct?
- DI publishes `document-processing-status-updated` + `document-processed` when configured?
- PC subscriptions + OIDC invoker alignment?

### Runs
- [ ] **Run 1:** GitHub `E2E Smoke Dev` **or** `./scripts/e2e-smoke-test.sh --env dev` — attach logs / run URL / commit SHA / timestamp.
- [ ] **Run 2:** repeat on a **different** day or `main` commit — attach same bundle of evidence.

### Done when
Both runs green; Gate D narrative pasted per `docs/runbooks/first-vertical-slice-exit-gates.md`; TAR-69 / memo §2 updated.
```

**Optional child issues (create under TAR-64 if work parallelizes):**

| Child title | Work type | Scope |
|-------------|-----------|--------|
| `TAR-64 / Verify Pub/Sub push wiring (DI → PC)` | Operator | GCP console + terraform vars per `m5-evidence-checklist` |
| `TAR-64 / Smoke run #1 evidence` | Operator | Attach artifact |
| `TAR-64 / Smoke run #2 evidence` | Operator | Attach artifact |
| `TAR-64 / Fix e2e script failure: <one-line>` | Agent-code | Only if reproducible bug in `scripts/e2e-smoke-test.sh` or workflow YAML |

---

### A3 — Update [TAR-85](https://linear.app/tart-baozi/issue/TAR-85) (remote MVP acceptance)

**Work type:** Operator

**Paste into issue:**

```markdown
## M5 handoff — acceptance (TAR-85)

### Goal
Fresh **remote** MVP acceptance against **dev** Cloud Run (or staging if operated), auditable JSON.

### Tasks
- [ ] Env URLs per `docs/setup/environment-strategy.md` (dev-first).
- [ ] Mint tokens per `docs/setup/gcp-local-cloud-run-auth.md` / `scripts/mint-cloud-run-tokens.sh`.
- [ ] `cd tools/evidara-cli && uv run evidara workflow mvp-acceptance` (or `--human` + save stdout).
- [ ] Confirm JSON includes `evidence_pack_version`.
- [ ] Attach output to this issue; link from TAR-69 / memo §2.

### Docs
- `docs/runbooks/mvp-acceptance-scenario-pack.md`
- `docs/runbooks/tar64-tar85-evidence-capture.md`
```

---

### A4 — Comment on [TAR-69](https://linear.app/tart-baozi/issue/TAR-69) + update memo (coordination, not code)

**Work type:** Operator / PM

**Paste into TAR-69 (comment):**

```markdown
## M5 bundle complete — links

- TAR-77: <url + note “screenshot attached”>
- TAR-64: <run1> , <run2>
- TAR-85: <mvp-acceptance json or log>

Next: update `docs/runbooks/phase-5-go-no-go-memo.md` §2 gate table (Result + Evidence link) in a small PR, or paste excerpt here and assign doc PR to release owner.
```

---

## Tier B — Phase 5 memo §7 (post-M5-path engineering; repo largely merged)

For each issue, **paste a checklist comment** if the issue body is stale; **close** if Linear scope is done and only execution remains elsewhere.

| Issue | Paste block |
|-------|-------------|
| [TAR-66](https://linear.app/tart-baozi/issue/TAR-66) | ```markdown\n## Status check (2026-04-12)\n- [ ] Confirm remaining scope: fixture-only vs new HTML edge cases.\n- [ ] If repo merged #195 and no further code: close or move residual to new issue.\n``` |
| [TAR-62](https://linear.app/tart-baozi/issue/TAR-62) | ```markdown\n## Agent handoff — promotion automation\n- [ ] Document current dev→(staging)→prod steps in runbook.\n- [ ] List gaps: Databricks bundle, Terraform, GitHub Environments.\n- [ ] Create child issues per gap (one PR-sized task each).\n``` |
| [TAR-63](https://linear.app/tart-baozi/issue/TAR-63) | ```markdown\n## Agent handoff — replay checkpoints\n- [ ] Verify `GET /v1/runs/{id}` replay_checkpoint meets operator needs; file issues for gaps.\n``` |
| [TAR-67](https://linear.app/tart-baozi/issue/TAR-67) | ```markdown\n## Operator execution — drills\nRunbooks merged ≠ drills executed.\n- [ ] Withdrawal drill — evidence: workflow URL + artifact per phase-5-go-no-go §2.1\n- [ ] DLQ triage drill — same\n- [ ] Alias rollback drill — same\n``` |
| [TAR-139](https://linear.app/tart-baozi/issue/TAR-139) | ```markdown\n## Agent handoff — discovery vs mutating APIs\n- [x] Inventory OpenAPI `agent-discovery` coverage vs desired CLI verbs (2026-04-25 snapshot).\n- [ ] File child issues for each missing read surface.\n\n### Coverage snapshot (2026-04-25)\nCurrent `agent-discovery` operations:\n- `contracts/api/platform-control.openapi.yaml` — 9 operations (sources list + runs/wizard read surfaces)\n- `contracts/api/legal-search.openapi.yaml` — 5 operations (search + document detail/read surfaces)\n\nCurrent `evidara workflow` verbs:\n- source: `inspect`, `propose`, `apply`, `verify`, `compensate`\n- search: `inspect`, `verify`\n- run: `status`, `evidence`\n\n### Gap map for child issues\n1. `workflow run resume` read + action support (CLI + contract-backed endpoint if required).\n2. `workflow run cancel` read + action support (CLI + contract-backed endpoint if required).\n3. Source approval/preview explicit read models to avoid overloading generic run lookups.\n4. Optional document-processing discovery surface if `workflow document *` is kept in TAR-139 scope.\n``` |

---

### TAR-139 inventory notes (agent prep, 2026-04-25)

This snapshot is intended to be pasted into TAR-139 before creating child issues.

| Area | Current coverage | Remaining work item |
|---|---|---|
| `workflow source inspect` | Partially covered by `agent-discovery` (`GET /v1/sources`). Current source-detail endpoint (`GET /v1/sources/{source_id}`) is not tagged `agent-discovery`. | Decide whether source detail should be tagged `agent-discovery` or avoided in agent-mode commands. |
| `workflow search inspect` and `workflow search verify` | Covered by `agent-discovery` (`GET /v1/search`, document detail/read paths in legal-search OpenAPI). | Keep as-is; file issue only if query-pack specific summaries are required server-side. |
| `workflow run status` and `workflow run evidence` | Covered by `agent-discovery` run read endpoints in platform-control OpenAPI. | Keep as-is; add schema-level evidence summary if operators need stronger guarantees. |
| Planned `workflow run resume` | Not yet represented as a CLI command; corresponding durable endpoint/contract is not tagged as `agent-discovery`. | Create child issue: contract-first endpoint + CLI wrapper + tests. |
| Planned `workflow run cancel` | Not yet represented as a CLI command; corresponding durable endpoint/contract is not tagged as `agent-discovery`. | Create child issue: contract-first endpoint + CLI wrapper + tests. |
| Proposed `workflow document *` family | Mentioned in architecture docs, not implemented in CLI command tree. | Create child issue only if still in TAR-139 scope after roadmap check. |

## Tier C — Metadata + relevance (parallel to M5; required for “demo truth”)

### C1 — [TAR-89](https://linear.app/tart-baozi/issue/TAR-89) children (recommended)

Create **three** child issues (titles suggested):

1. **`TAR-89 / Data path — bundle + DI hints`** — Agent-code + platform-control/DI; exit = track 1 in [tar-89-workstreams](tar-89-workstreams.md).
2. **`TAR-89 / Serving path — projections + UI metadata`** — Agent-code legal-search; exit = track 2.
3. **`TAR-89 / Environment truth — replay + re-index + 3.5.3 sign-off`** — Operator-heavy; exit = track 3 + [metadata-quality-plan-status](metadata-quality-plan-status.md) §3.5.3.

**Paste into each child:**

```markdown
## Parent
TAR-89 — metadata credibility

## Canonical acceptance
Do not fork bullets — follow `docs/runbooks/metadata-quality-plan-status.md` section **3.5** (and issue description). Edit that doc first if acceptance moves, then mirror here.

## Links
- `docs/runbooks/tar-89-workstreams.md` (this child maps to track N)
```

### C2 — [TAR-82](https://linear.app/tart-baozi/issue/TAR-82) / [TAR-68](https://linear.app/tart-baozi/issue/TAR-68)

**Paste:**

```markdown
## M5-adjacent — relevance baseline evidence

- [ ] Run query pack per `docs/runbooks/search-relevance-baseline.md` against **dev** (or staging) legal-search API.
- [ ] Paste Markdown table into issue + link from phase-5-go-no-go memo §3.
- [ ] Work type: Operator (data) unless automating script → then Agent-code in `scripts/`.
```

---

## Tier D — Full product GO ([mvp-demo-release-recommendation](mvp-demo-release-recommendation.md) §Final Release Gate)

### D1 — [TAR-87](https://linear.app/tart-baozi/issue/TAR-87) & [TAR-88](https://linear.app/tart-baozi/issue/TAR-88)

**Paste (each):**

```markdown
## Full GO handoff

### Goal
Walkthrough evidence attached per `docs/runbooks/mvp-demo-release-recommendation.md` §Final Release Gate item 1.

### Tasks
- [ ] Execute walkthrough scenarios tied to this issue’s scope (see issue title).
- [ ] Attach screenshots / recordings per `docs/runbooks/mvp-website-walkthrough.md`.
- [ ] Link strict `Release Readiness` artifact + interaction-flow evidence.

### Done when
No open **blocker** severity items remain for this scope on walkthrough doc.
```

---

## Tier E — Agent-code epics (file as new Linear issues if missing)

These close gaps called out in `docs/components/document-intelligence-implementation-plan.md` **minimal next tasks** and CI posture — **not** automatically part of M5 evidence.

### E1 — `DI — CI/CD: Databricks Asset Bundle + Terraform promotion`

**Work type:** Agent-code (infra + CI YAML)

**Description template:**

```markdown
## Problem
Document intelligence implementation plan still lists Terraform + Asset Bundle deployment integration as open.

## Scope (suggested slices — one PR each)
1. Document current manual promotion path in `docs/` (short runbook section).
2. GitHub workflow: validate bundle (`databricks bundle validate`) on PR path filters.
3. Optional: workflow_dispatch promotion to non-prod with approval gate.

## Acceptance
- [ ] Plan checkbox updated or issue linked from `document-intelligence-implementation-plan.md`
- [ ] CI green; rollback/doc note if workflow is noop without secrets

## Paths
- `document-intelligence/databricks/`
- `.github/workflows/`
- `docs/runbooks/`
```

### E2 — `Release Readiness — dev-first env alignment audit`

**Work type:** Agent-code (docs + workflow vars)

**Description template:**

```markdown
## Problem
Phase 5 memo §2.1: strict Release Readiness must target correct GitHub Environment + E2E workflow names for dev-first orgs.

## Tasks
- [ ] Verify `RELEASE_READINESS_GITHUB_ENVIRONMENT`, `RELEASE_READINESS_E2E_SMOKE_WORKFLOW` against live GitHub settings.
- [ ] PR to document actual values in `docs/runbooks/runtime-stack.md` §7 (no secrets).

## Acceptance
- [ ] Linked from TAR-77 / TAR-69 as “configuration source of truth”
```

### E3 — `legal-search — projection replay automation hook`

**Work type:** Agent-code (optional; speeds TAR-89)

```markdown
## Problem
Metadata plan: stale OpenSearch rows after projection changes.

## Scope
- [ ] Script or documented one-liner to replay projections for ID set (dev).
- [ ] Link from `docs/runbooks/staging-projection-replay.md` or dev equivalent.

## Acceptance
- [ ] Operator can refresh demo corpus without re-running full DI
```

---

## Agent coding prompt (attach to any **Agent-code** issue)

```text
You are working in the Evidara monorepo. Read AGENTS.md and the issue links below before changing code.

Constraints:
- Small, production-safe PRs; contract-first if APIs change.
- Add the narrowest test that proves the change.
- Update runbooks only if operator flow or env vars change.

Deliverables:
1. Implementation + tests
2. PR description: what changed, why, how to verify (commands with paths from repo root)
3. Link this PR back to the Linear issue ID in the PR body
```

---

## Verification checklist for the human (after Linear is populated)

- [ ] Every **Tier A** issue has **checkboxes** and **linked evidence** (no empty “done”).
- [ ] **TAR-69** has a single **summary comment** linking A1–A3 when M5 is green.
- [ ] **TAR-89** has **three children** (or explicit reason not to split).
- [ ] **Tier D** issues exist or are waived with written risk acceptance on TAR-69.
- [ ] **Tier E** issues created only if in-scope for this release train; otherwise mark `Later`.
