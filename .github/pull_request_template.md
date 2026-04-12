## Summary

<!-- Describe what this PR does and why. -->

## Change Classification

<!-- Check all that apply. -->

- [ ] `internal-refactor`
- [ ] `user-visible-behavior`
- [ ] `contract-change`
- [ ] `infra-change`
- [ ] `pipeline-change`
- [ ] `architecture-change`
- [ ] `docs-only`

## Affected Components

<!-- Check all that apply. -->

Parallel streams by component: [docs/process/parallel-work-streams.md](docs/process/parallel-work-streams.md).

- [ ] `platform-control`
- [ ] `document-intelligence`
- [ ] `legal-search`
- [ ] `contracts`
- [ ] `infra`
- [ ] `docs`
- [ ] `scripts`
- [ ] `tools/evidara-cli`

## Work stream coordination

<!-- When two PRs touch the same OpenAPI file, migration, or cross-service behavior, one stream leads — link it here. -->

- [ ] N/A — no shared seam with another in-flight change
- [ ] Coordinating PR or owner: <!-- link and/or @handle -->

## Sync Impact

<!-- Updated where applicable: -->

- [ ] Tests
- [ ] Docs
- [ ] Contracts (OpenAPI / JSON Schema)
- [ ] Architecture (`structurizr/workspace.dsl`, ADRs)
- [ ] Infra docs

## Why No Updates Were Needed

<!-- If any applicable sync item was NOT updated, explain why here. Delete this section if all relevant items were updated. -->

N/A

## Checklist

- [ ] PR title follows conventional commit format (`feat:`, `fix:`, etc.)
- [ ] `pre-commit run --all-files` passes
- [ ] CI should pass
- [ ] Backwards compatible (or breaking changes documented above)
- [ ] If this PR touches `tools/evidara-cli/**`, `scripts/check-evidara-cli.sh`, `scripts/smoke-evidara-cli.sh`, `.github/workflows/evidara-cli.yml`, or `.github/workflows/evidara-cli-remote-smoke.yml`: ran `pre-commit run evidara-cli-check --all-files` (or full `pre-commit run --all-files`)

## Scraping / Acquisition QA (Platform-Control Only)

<!-- Complete this section when scraping/acquisition behavior changes. See docs/testing/scraping-qa-standard.md -->

- [ ] Not applicable (no scraping/acquisition behavior change)
- [ ] `scraping-qa` workflow is green on this PR (required status check on `main`)
- [ ] Contract validation updated/passing for bundle + `artifact_bundle.available` boundary
- [ ] Golden fixture updated/added, or explicitly unchanged and verified
- [ ] Provider canary/integration path covered by tests
- [ ] Idempotency behavior covered (duplicate webhook/event path)
- [ ] Failure-mode test added/updated or explicitly not impacted
- [ ] Staging smoke impact considered (or follow-up tracked)

## Reviewer Notes

<!-- Anything the reviewer should pay special attention to. -->
