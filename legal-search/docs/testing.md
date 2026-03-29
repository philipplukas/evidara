# Testing Strategy (1–3 Person Team)

This strategy optimizes for speed, confidence, and low maintenance for a small team.

## Test layers

1. **Unit tests (majority)**
   - Reducers and state transitions
   - Mapping functions (domain/search payload -> view models)
   - Utility functions

2. **Integration tests (selective)**
   - BFF controller + service + repository/mock OpenSearch client
   - Frontend API hook integration with generated OpenAPI client

3. **E2E smoke tests (few, critical paths only)**
   - Search -> open detail -> pivot -> back
   - Filter + context changes

## Coverage policy

Use risk-based thresholds:

- Global: **>= 70%**
- Critical modules (search mapping, contract adapters, auth, query builders): **>= 85%**

Do not chase 100% coverage; prioritize failure-prone and business-critical logic.

## Contract testing

Treat OpenAPI as a release artifact:

- Lint contract on every PR
- Regenerate client on every PR
- Fail CI if generated output is stale
- Add compatibility checks before breaking contract changes

## CI and pre-commit alignment

Pre-commit must be a fast subset of CI.

### Pre-commit (fast)

- Lint staged files
- Typecheck (if quick enough for developer machines)
- OpenAPI lint when contract changed

### CI (full)

- Install dependencies
- Lint
- Typecheck
- Unit tests
- Integration tests
- Contract lint + generation drift check

## Ownership cadence

For a 1–3 person team:

- Keep one default reviewer for contract changes
- Rotate weekly ownership of flaky/failing tests
- Keep test failures as merge blockers
