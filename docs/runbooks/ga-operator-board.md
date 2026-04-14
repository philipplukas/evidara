# GA operator board

Owner: Platform / release
Last reviewed: 2026-04-14
Last verified: 2026-04-14
Applies to: GA readiness coordination after the 2026-04-13 merge wave

## Purpose

This runbook is the operator-facing board for the next GA phase. It consolidates the
active release, policy, reliability, acceptance, and relevance lanes into one place so
operators can see what to push now, what can run in parallel, and what should remain
tracked under the GA umbrella.

This board does not replace the underlying lane notes. It gives the release owner one
working view across:

- `TAR-214` - release evidence refresh
- `TAR-70` - gate policy hardening
- `TAR-238` - runner reliability
- `TAR-239` - five-country acceptance A
- `TAR-240` - five-country acceptance B
- `TAR-241` - relevance baseline
- `TAR-160` - GA umbrella and final sign-off

## Current posture

What is already true:

- The implementation merge wave is complete.
- The immediate shift is from shipping code to proving release readiness and GA quality.
- The `rocky-agents` staging proof is now strong enough to count as platform evidence:
  `rocky-agents-staging` is back on `main`, Argo is `Healthy` / `Synced`, and live
  `github-app` is on `ghcr.io/philipplukas/rocky-agents-github-app:sha-c7f70ad135cd`.
- The main remaining work is evidence, branch-gate policy hardening, runner trust, and
  five-country acceptance confidence.

What is not yet true:

- The M5 release packet is not fully refreshed.
- The branch-gate model is not yet in its intended steady state.
- Runner stability is improved but not yet trusted as a solved problem.
- Five-country acceptance and relevance still need current evidence attached to the GA
  umbrella, but CH and AT now have live fast-loop run evidence on dev.
- The current dev relevance signal no longer has an empty `q=*` control row; the dev
  index returns results again, but the agreed seed queries still collapse to generic
  top hits, which now points more to retrieval / projection quality than pure alias
  emptiness. The follow-up stays on `TAR-242`.

## Board status

| Lane | Linear | Status | Push now? | Exit condition |
|------|--------|--------|-----------|----------------|
| Release evidence refresh | `TAR-214` | active | yes | `TAR-64`, `TAR-77`, `TAR-85`, phase-5 memo, and `TAR-69` are refreshed and linked |
| Gate policy hardening | `TAR-70` | active | yes | required-check model is agreed, documented, and validated against representative PR types |
| Runner reliability | `TAR-238` | active | yes | light/heavy pools are stable across rotation and preflight checks pass reliably |
| Five-country acceptance A (CH + AT) | `TAR-239` | active | track in parallel | CH/AT checklist is executed and evidence is attached into `TAR-160` |
| Five-country acceptance B (DE + FR) | `TAR-240` | ready | track in parallel | DE/FR checklist is executed and evidence is attached into `TAR-160` |
| Relevance baseline | `TAR-241` | active | yes | query pack is rerun with the `q=*` control row, result table is attached, and regressions are split into follow-up issues |
| GA umbrella / final sign-off | `TAR-160` | collecting | no, assemble after inputs land | consolidated GA evidence pack and release decision are ready |

## What to push now

These lanes deserve direct operator attention immediately because they unblock or
de-risk the entire GA board:

### 1. `TAR-214` - release evidence refresh

Why now:

- It is the closest thing to a release-critical lane.
- The release packet still looks incomplete until the evidence is reattached.

Immediate operator actions:

1. Re-verify `TAR-77` with current branch-protection proof and one green strict
   `Release Readiness` run.
2. Refresh `TAR-64` if we want a fully current packet instead of relying on the most
   recent historical evidence.
3. Refresh `TAR-85` with a new `evidara workflow mvp-acceptance` run and confirm
   `evidence_pack_version`.
4. Mirror the refreshed links into
   [`phase-5-go-no-go-memo.md`](phase-5-go-no-go-memo.md).
5. Post the final summary linkage comment into `TAR-69`.
6. Treat [PR #220](https://github.com/philipplukas/evidara/pull/220) as the current CI/auth unblocker for fresh `main` evidence runs.

### 2. `TAR-70` - gate policy hardening

Why now:

- The merge wave exposed a real mismatch between branch protection and emitted checks.
- We should not carry that ambiguity toward GA.

Immediate operator actions:

1. Use [`tar-70-gate-policy-hardening.md`](tar-70-gate-policy-hardening.md) as the
   recovery plan.
2. Audit which workflows emit on every PR versus only on selected paths.
3. Keep universal required checks limited to always-on contexts.
4. Treat `Release Readiness` and `scraping-qa` as release gates unless and until an
   always-on aggregator exists.
5. Validate the chosen model against docs-only, code, and infra PR shapes before
   calling the policy stable.

### 3. `TAR-238` - runner reliability

Why now:

- Release evidence and PR trust both depend on stable runner behavior.
- The recent ARC incidents are documented, but the steady-state needs proving.

Immediate operator actions:

1. Use the runner reliability checklist in
   [`ci-actions-duration-metrics.md`](ci-actions-duration-metrics.md#runner-reliability-checklist).
2. Keep the Hetzner + Tailscale kubeconfig path as the standard cluster access path for
   `evidare-staging`; the live proof is recorded in
   [`github-app-proof-rerun-checklist.md`](github-app-proof-rerun-checklist.md).
3. Prove both light and heavy pools with `runner-bootstrap-preflight.yml`.
4. Re-run `runner-pool-smoke.yml` after any recycle or scale-set change.
5. Keep `runtime-images.yml` off the generic pool until Docker/buildx is repeatedly
   stable.
6. Treat label drift, ghost-busy state, or queue stalls as runner-registration issues
   first, not workflow-selector issues.
7. Keep the remaining proof gap explicit: no named Temporal execution ID has been captured yet.

### 4. `TAR-241` - relevance baseline

Why now:

- It can run in parallel with the evidence and policy lanes.
- It feeds the GA quality story without blocking the assembly of the umbrella packet.

Immediate operator actions:

1. Run the agreed query pack from
   [`staging-relevance-query-pack-suggestions.md`](staging-relevance-query-pack-suggestions.md)
   with [`scripts/run-staging-relevance-query-pack.sh`](../../scripts/run-staging-relevance-query-pack.sh).
2. Keep the `q=*` control row in the pack and record `totalResults` so we can distinguish
   ranking issues from serving / corpus drift.
3. Replay at least one known-good CH/AT document when projection logic changes so we can
   separate metadata/title regressions from broad ranking debt.
4. Record results using
   [`relevance-eval-result-template.md`](relevance-eval-result-template.md).
5. Attach the result table to `TAR-82` and `TAR-68`.
6. Keep `TAR-242` only for true serving / corpus drift. The current dev issue is broader
   ranking quality, not an empty control row.

Current April 14 status:

- Dev Document Service wiring is restored.
- Targeted replays now prove that CH/AT metadata is materially healthier:
  - `doc_7m5fzs4ksj057ft0sgzqaecpyh` (AT RIS) now indexes as `law` and stays rank 1 for
    `Produktdeklaration`, `BGBl. Nr. 43/1975`, and `RIS Dokument`.
  - `doc_1wxstrwdxtwh0zaxag6x37hya2` (CH Fedlex) now indexes as `law`, and title extraction
    uses the embedded Fedlex title:
    `Bundesverfassung der Schweizerischen Eidgenossenschaft vom 18. April 1999`.
- The remaining weak results for `Bundesgericht`, `Art. 8 EMRK`, and `BVGE` are therefore
  ranking / wider-corpus quality debt, not metadata/title drift on the replayed docs.

## What stays tracked in parallel

These lanes should stay moving, but they do not need to steal focus from the release
evidence, policy, and runner work in the same hour:

### `TAR-239` - five-country acceptance A (CH + AT)

Working note:

- [`five-country-acceptance-a.md`](five-country-acceptance-a.md)

Use this lane to:

- validate CH/AT taxonomy, filters, subtitles, detail rows, and operator flow
- capture CH/AT-specific gaps for canton aliases, authority naming, and multilingual drift
- attach a compact summary into `TAR-160`

Current evidence highlights:

- CH live SPARQL fast-loop proof is already recorded in
  [`2026-04-13-ch-fedlex-sparql-preview-run1.md`](evidence/2026-04-13-ch-fedlex-sparql-preview-run1.md)
- AT now has clean live RIS fast-loop proof for:
  - narrow run `run_01kp5xqgrfyqq2abez3r666d9h`
  - tiny batch run `run_01kp5xrqvh61xfdace1x9sqed1`
- AT recovery also surfaced an important operator invariant:
  `platform-control-worker` must keep GCS artifact-store and Pub/Sub env parity with
  `platform-control-api`, or DI cannot read worker-published bundle manifests

### `TAR-240` - five-country acceptance B (DE + FR)

Working note:

- [`five-country-acceptance-de-fr.md`](five-country-acceptance-de-fr.md)

Use this lane to:

- validate DE/FR taxonomy, shared label meaning, subtitles, detail behavior, and operator flow
- capture translation, mapping, and overlay drift separately from contract issues
- attach a compact summary into `TAR-160`

## Serialized choke points

Do not parallelize these across multiple owners at once:

1. Live branch-protection changes
2. Shared global workflow edits under `.github/workflows/`
3. The final `phase-5-go-no-go-memo.md` recommendation update
4. The final `TAR-160` GA sign-off comment

## Suggested execution order

1. Finish `TAR-214`.
2. Lock the `TAR-70` target policy model.
3. Prove `TAR-238` runner stability on both pools.
4. Run `TAR-241` and attach the baseline evidence.
5. Execute `TAR-239` and `TAR-240` and roll their summaries into `TAR-160`.
6. Assemble the final GA packet in `TAR-160`.

## Evidence map

| Need | Source |
|------|--------|
| Release packet and go/no-go wording | [`phase-5-go-no-go-memo.md`](phase-5-go-no-go-memo.md) |
| Evidence checklist for TAR-64 / TAR-77 / TAR-85 | [`phase-5-evidence-checklist.md`](phase-5-evidence-checklist.md) |
| Friction and acceleration priorities | [`friction-and-acceleration-map.md`](friction-and-acceleration-map.md) |
| Gate policy recovery plan | [`tar-70-gate-policy-hardening.md`](tar-70-gate-policy-hardening.md) |
| Runner stabilization and verification | [`ci-actions-duration-metrics.md`](ci-actions-duration-metrics.md#runner-reliability-checklist) |
| Hetzner / Tailscale / Argo platform proof | [`github-app-proof-rerun-checklist.md`](github-app-proof-rerun-checklist.md) |
| CH + AT acceptance lane | [`five-country-acceptance-a.md`](five-country-acceptance-a.md) |
| DE + FR acceptance lane | [`five-country-acceptance-de-fr.md`](five-country-acceptance-de-fr.md) |
| Relevance baseline and result template | [`search-relevance-baseline.md`](search-relevance-baseline.md), [`relevance-eval-result-template.md`](relevance-eval-result-template.md) |

## Done means

The board is ready to roll into a final GA sign-off when all of these are true:

- `TAR-214` evidence is fresh and linked
- `TAR-70` policy is no longer drifting from actual emitted checks
- `TAR-238` runner trust is re-established
- `TAR-239` and `TAR-240` have attached country-slice evidence
- `TAR-241` has a current relevance table plus follow-up tickets for any regressions
- `TAR-160` can be read end-to-end without relying on tribal context
