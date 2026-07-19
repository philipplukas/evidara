# Testing Documentation

## Purpose

This directory contains Evidara's testing strategy, principles, and guides. Testing documentation is split into two levels:

- **Shared testing docs** (`docs/testing/`) — cross-cutting strategy that applies to all components
- **Component-specific testing docs** (`docs/components/testing/`) — concrete per-component testing instructions

## Shared Testing Strategy

| Document | Purpose |
|----------|---------|
| [Testing Principles](testing-principles.md) | Core philosophy and test type definitions |
| [Testing Levels](testing-levels.md) | What each testing level catches and when to use it |
| [Drift Detection](drift-detection.md) | Detecting and recovering from drift |
| [Golden Datasets](golden-datasets.md) | Strategy for representative test data |
| [CI Testing Strategy](ci-testing-strategy.md) | What runs in CI and when |
| [Minimal Test Matrix](minimal-test-matrix.md) | Smallest credible test set for the whole platform |
| [First End-to-End Slice](first-end-to-end-slice.md) | The first full-path E2E test |
| [E2E Run Isolation](e2e-run-isolation.md) | How a Playwright run proves it is talking to the server it started (per-run nonce, opt-in reuse, per-lane ports) |
| [Scraping QA Standard](scraping-qa-standard.md) | Team-realistic quality gate for acquisition/scraping, including temporary manual merge enforcement when required checks are unavailable |
| [First Vertical Slice Exit Gates](../runbooks/first-vertical-slice-exit-gates.md) | Runtime pass/fail gate and latest evidence for source -> DI -> search |

## Component Testing Guides

| Component | Guide |
|-----------|-------|
| platform-control | [Platform Control Testing](../components/testing/platform-control-testing.md) |
| document-intelligence | [Document Intelligence Testing](../components/testing/document-intelligence-testing.md) |
| legal-search | [Legal Search Testing](../components/testing/legal-search-testing.md) |
| contracts | [Contracts Testing](../components/testing/contracts-testing.md) |
| infra | [Infra Testing](../components/testing/infra-testing.md) |

## How to Use These Docs

1. **Start with [Testing Principles](testing-principles.md)** to understand the philosophy.
2. **Read [Testing Levels](testing-levels.md)** to understand what types of tests exist and when they matter.
3. **Check the [Minimal Test Matrix](minimal-test-matrix.md)** to see what the MVP requires.
4. **Open the component guide** for the area you are working on.
5. **Refer to [CI Testing Strategy](ci-testing-strategy.md)** when configuring pipelines.
6. **Use run-scoped runtime smoke checks** from the first vertical slice runbook when validating live environments.

## Design Principles

- Practical over comprehensive — document what helps, skip what doesn't
- Phased — clearly separate MVP requirements from later expansion
- Small-team optimized — 1–3 person team, limited bandwidth for test maintenance
- AI-compatible — AI-generated code must meet the same testing bar as human-written code
