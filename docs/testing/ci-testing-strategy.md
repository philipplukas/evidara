# CI Testing Strategy

## Purpose

Define what tests run in CI, when they run, and how they gate deployments.

> **The tables below describe intent. What CI actually runs is decided by
> `.github/workflows/` and the `scripts/check-*.sh` gates.** Where the two
> disagree, the workflows win and this document is wrong.
> [ADR-0040](../adr/0040-test-result-trust.md) exists because that gap was real:
> specs were committed, linted, and typechecked while no job could reach them.
> `scripts/check_test_reachability.py` now derives the answer from the workflows
> and fails the build on any unregistered unreachable test file — consult it,
> not this page, for the current truth.

## Guiding Principles

- **Do not block development with expensive flaky tests.** A flaky test that blocks CI is worse than no test.
- **Expensive tests may run on merge or nightly.** Not everything needs to run on every commit.
- **Smoke tests should be fast and deterministic.** If a smoke test is slow or flaky, it is not a smoke test.
- **CI should give confidence, not slow you down.** A small team cannot afford 30-minute CI pipelines on every push.

---

## MVP CI Pipeline

Run on every push and PR. Must be fast (target: under 5 minutes).

### What runs

| Check | Component | Blocks PR |
|-------|-----------|:-:|
| Schema validation | contracts | ✅ |
| Contract validation (example payloads) | contracts | ✅ |
| Unit tests | all components | ✅ |
| Linting / formatting | all components | ✅ |
| Terraform format check | infra | ✅ |
| Terraform validate | infra | ✅ |
| Minimal smoke tests | platform-control, document-intelligence | ✅ |

### What does NOT run in MVP CI

- Integration tests requiring a database or external service
- Golden dataset tests (if slow)
- End-to-end tests
- Deployment steps

---

## Later CI Expansion

Add these as the platform matures and the team has infrastructure for them.

### On PR (expanded)

| Check | Component | Blocks PR |
|-------|-----------|:-:|
| Component integration tests | platform-control, document-intelligence | ✅ |
| Golden dataset tests | document-intelligence | ✅ |
| OpenSearch mapping validation | legal-search | ✅ |
| API contract tests | legal-search, platform-control | ✅ |

### On merge to main

| Check | Component | Blocks deploy |
|-------|-----------|:-:|
| End-to-end slice test | cross-component | ⚠️ (advisory initially) |
| Reindex smoke test | legal-search | ⚠️ |
| Terraform plan | infra | ✅ |

### Nightly

| Check | Purpose |
|-------|---------|
| Full golden dataset run | Catch subtle regressions |
| Drift detection checks | Detect source or semantic drift |
| Indexing parity check | Verify search index matches canonical data |
| Distribution checks | Monitor aggregate statistics |

---

## CI Configuration Guidelines

### Keep CI fast

- Parallelize independent checks
- Cache dependencies aggressively
- Use pre-built test containers where possible
- Separate fast checks (lint, schema, unit) from slow checks (integration, E2E)

### Handle flakiness

- If a test fails non-deterministically more than once, mark it as flaky and move it to nightly
- Never leave a flaky test blocking PRs — fix it or quarantine it
- Track flaky tests and fix them within one sprint

### Environment management

- MVP CI runs without external services (pure unit + schema tests)
- Integration and E2E tests require a test environment (local containers or dedicated CI environment)
- Never run tests against production data or services

---

## CI Pipeline Structure (Target)

```text
push / PR
  ├── lint + format (all components)
  ├── schema validation (contracts)
  ├── unit tests (all components)
  ├── terraform validate (infra)
  └── smoke tests (fast)

merge to main
  ├── all PR checks
  ├── integration tests
  ├── golden dataset tests
  ├── E2E slice test
  └── terraform plan

nightly
  ├── full golden dataset run
  ├── drift detection
  ├── indexing parity
  └── distribution checks
```

---

## Metrics to Track

Once CI is running, track:

- **CI pass rate** — should stay above 95%
- **CI duration** — PR pipeline should stay under 5 minutes
- **Flaky test count** — should trend toward zero
- **Test count by level** — ensure coverage grows with the codebase
