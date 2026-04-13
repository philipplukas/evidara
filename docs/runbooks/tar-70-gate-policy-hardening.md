# TAR-70 gate policy hardening

Owner: Platform / release  
Last reviewed: 2026-04-13  
Last verified: 2026-04-13  
Applies to: GitHub branch protection, PR-required checks, release-lane gating

## Purpose

This runbook captures the steady-state required-check model after the merge-wave branch-protection drift that blocked `main` during the TAR-89 / release-evidence stack. The live GitHub state we want to preserve is:

- `main` stays strict (`strict: true`)
- universal required checks are always-on checks only
- `Release Readiness` and `scraping-qa` stay release gates unless we add an always-on aggregator workflow

It is intentionally narrow: it documents the required-check model we want going forward and the rollout/validation steps, without changing live branch protection itself.

## 1. Current policy problem

The repo has two different kinds of CI signals:

1. **Always-on PR checks** that emit on every pull request, such as `PR Title` and `Docs and Contracts / contract-validation`.
2. **Path-filtered or release-only checks** that only emit for some PRs or on schedules/manual dispatch, such as:
   - `Legal Search / api`
   - `Legal Search / frontend`
   - `Platform Control / check`
   - `Document Intelligence / document-intelligence-check`
   - `Document Intelligence / document-intelligence-runtime-check`
   - `Terraform / *`
   - `Release Readiness / release-readiness`
   - `scraping-qa`

During the merge wave, `main` branch protection was effectively asking GitHub to require contexts that do not exist on every PR. That produced blocked merges even when the visible PR checks were green.

The steady-state rule is simple: keep `main` strict, but require only checks that emit on every PR. Do not make a path-filtered or release-only workflow a universal required status check unless the workflow emits a stable context on every PR.

## 2. Steady-state target model

Use three layers instead of one overloaded branch-protection rule:

1. **Universal PR gate**
   - Require only checks that are guaranteed to emit on every PR.
   - Keep this set small and stable.
   - Prefer a single aggregator-style gate if we add one later.

2. **Path-specific PR gates**
   - Keep component workflows path-filtered.
   - Let them block only the PRs that actually trigger them.
   - Do not require them universally in branch protection unless they emit on all PRs.

3. **Release-lane gates**
   - Keep `Release Readiness` and `scraping-qa` as release / evidence gates.
   - Use them for go/no-go, Linear evidence, and mainline release posture.
   - Do not treat them as universal PR-required checks unless they are redesigned to emit on every PR.

If we want a stricter future state, the safest end-state is a single always-on merge-gate workflow that fans out to the relevant subchecks but always publishes one stable required context. Until that exists, the conservative model is to keep branch protection minimal and stable.

For a concrete operator matrix of PR types versus emitted checks, see
[tar-70-emitted-check-matrix.md](tar-70-emitted-check-matrix.md).

## 3. Exact implementation steps

1. Audit the workflows that currently emit on every PR versus only on selected paths.
2. Keep the universal required-check list limited to checks that always emit.
3. Keep release-only and path-filtered contexts out of universal branch protection unless they are wrapped by an always-on aggregator.
4. Keep `Release Readiness` and `scraping-qa` as release evidence gates, not generic PR blockers.
5. Align `docs/setup/branch-rules.md`, `docs/runbooks/runtime-stack.md`, and the release memo after the policy is finalized.
6. If we decide to add an aggregator, implement it as a new workflow that always runs on PRs and emits one stable required context.
7. Use the emitted-check matrix to verify each PR archetype before changing branch protection.

## 4. Validation plan

1. Create a matrix of PR types and verify which checks emit:
   - docs-only PR
   - legal-search code PR
   - platform-control code PR
   - document-intelligence PR
   - infra / Terraform PR
2. Confirm that the universal required checks appear on every PR.
3. Confirm that path-filtered checks only gate the PRs that actually trigger them.
4. Re-run release-lane evidence on `main`:
   - `Release Readiness`
   - `scraping-qa` where relevant
5. Recheck a merge wave against a docs-only PR and a code PR to confirm there is no branch-protection drift.

## 5. Files and tickets touched

### Files

- [`docs/runbooks/tar-70-gate-policy-hardening.md`](tar-70-gate-policy-hardening.md)
- [`docs/runbooks/tar-70-emitted-check-matrix.md`](tar-70-emitted-check-matrix.md)
- [`docs/setup/branch-rules.md`](../setup/branch-rules.md) for the eventual policy alignment
- [`docs/runbooks/runtime-stack.md`](runtime-stack.md) for release-gate wording
- [`docs/runbooks/phase-5-go-no-go-memo.md`](phase-5-go-no-go-memo.md) for release evidence references

### Linear

- `TAR-70` - gate policy hardening
- `TAR-214` - release evidence refresh
- `TAR-160` - GA sign-off umbrella
- `TAR-82` / `TAR-68` - relevance baseline

## Notes

- This runbook is a recovery plan, not a live branch-protection change.
- The branch-protection rule should only be updated once the chosen required-check model is agreed and validated against a representative PR matrix.
