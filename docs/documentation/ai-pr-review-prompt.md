# AI PR Review Prompt for Documentation and Contract Drift

Review this pull request for possible documentation and contract drift.

Focus on these questions:

## 1. Architecture drift

- Did this PR change component boundaries, storage choices, communication patterns, or ownership?
- If yes, should `docs/architecture/` or an ADR in `docs/adr/` be updated?

## 2. Contract drift

- Did this PR change API payloads, event payloads, IDs, or shared entity shapes?
- If yes, were the relevant files in `contracts/api/`, `contracts/schemas/`, or `contracts/events/` updated?
- Are example payloads or related prose docs now stale?

## 3. Component doc drift

- Did this PR change the actual scope or behavior of:
  - platform-control
  - document-intelligence
  - legal-search
  - contracts
  - infra
- If yes, should the corresponding file in `docs/components/` be updated?
- Does the PR introduce future-state behavior but fail to distinguish it from current-state documentation?

## 4. Testing doc drift

- Did this PR materially change testing expectations, test commands, drift detection logic, or CI checks?
- If yes, should `docs/testing/` or `docs/components/testing/` be updated?

## 5. Setup/runbook drift

- Did this PR change developer setup, deployment, reindexing, operations, or recovery procedures?
- If yes, should `docs/setup/` or `docs/runbooks/` be updated?
- Do runbooks that are affected need a new `Last verified` date?

## 6. Search/projection drift

- If search projection logic changed, did `legal-search` docs and tests remain aligned?
- If canonical document fields changed, did search projection contracts and index expectations remain aligned?

## 7. Minimality and clarity

- Is any documentation describing planned future behavior as if it already exists?
- Is any prose duplicating contract truth that should instead reference the source contract files?

## Output format

Provide:

1. A short summary
2. A list of likely missing doc or contract updates
3. A confidence rating: high / medium / low
4. If nothing seems missing, say so explicitly
