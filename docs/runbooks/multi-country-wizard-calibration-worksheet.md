# Multi-Country Wizard Calibration Worksheet

Owner: Platform team  
Last reviewed: 2026-04-07  
Applies to: CH, AT, DE, FR, IT rollout waves

## Purpose

Provide an operator-friendly worksheet to calibrate shard strategy and review thresholds per country during the first two weeks of rollout.

This worksheet is used after initial wizard deployment and before locking country-specific defaults.

## Baseline defaults (starting point)

- `highThreshold = 0.90`
- `lowThreshold = 0.70`
- default shard strategy:
  - high complexity countries: `country_jurisdiction_authority`
  - medium complexity countries: `country_jurisdiction`
  - low complexity countries: `country_only`

## Data collection window

Collect at least 14 days of evidence per country with:

- at least 10 preview runs
- at least 5 production runs
- at least 200 reviewed records for countries with mandatory-review activity

Do not promote or demote shard strategy before minimum evidence is met.

## Weekly calibration metrics

Track these metrics per country and per shard strategy:

1. `run_completion_slo_breach_rate` (target: <= 5%)
2. `review_freshness_slo_breach_rate` (target: <= 10%)
3. `critical_field_audit_error_rate` (target: < 2%)
4. `state_duration_skew_ratio_p95` (target: <= 4.0)
5. `retry_density_per_1000_nodes` (target: stable/decreasing)
6. `mandatory_review_rate` (target: stable/decreasing with quality)
7. `taxonomy_drift_incidents_per_week` (target: stable/decreasing)

## Promotion and demotion rules

### Promote to finer-grained sharding

Promote from `country_jurisdiction` to `country_jurisdiction_authority` when all are true for two consecutive weeks:

- `state_duration_skew_ratio_p95 > 4.0` OR one shard repeatedly dominates p95 latency
- run SLO breach rate is above target
- backlog growth is concentrated in a small subset of authorities

### Demote to coarser-grained sharding

Demote from `country_jurisdiction_authority` to `country_jurisdiction` when all are true for two consecutive weeks:

- SLO targets are met
- shard skew remains <= 2.0
- operator overhead (triage + approvals) increases without quality gains

Never demote below `country_jurisdiction` for countries with persistent dual-track administrative/judicial complexity.

## Threshold tuning rules

### Raise `highThreshold` by +0.02 (max 0.95) when:

- audited error rate for auto-accepted records exceeds 2% for 2 weeks
- reviewer edits concentrate in one or two critical fields

### Lower `highThreshold` by -0.02 (min 0.85) when:

- audited auto-accepted error rate remains < 1% for 2 weeks
- review backlog breaches freshness SLO while quality remains stable

### Raise `lowThreshold` by +0.02 (max 0.80) when:

- downstream incidents are linked to low-confidence accepted records

### Lower `lowThreshold` by -0.02 (min 0.60) when:

- mandatory review queue becomes persistent bottleneck with low disagreement rates

Adjust one threshold at a time and re-measure for one week.

## Country worksheet template

Use one section per country per week.

```text
Country:
Week range:
Current shard strategy:
Current thresholds: high= , low=

Run metrics:
- RunCompletionSLO breach rate:
- ReviewFreshnessSLO breach rate:
- PublishQuality audited error rate:

Execution metrics:
- state_duration_skew_ratio_p95:
- retry_density_per_1000_nodes:
- dominant slow shard(s):

Review metrics:
- mandatory_review_rate:
- review disagreement_rate:
- backlog_age_p95:

Drift metrics:
- taxonomy_drift_incidents:
- unresolved_drift_items:

Decision:
- keep / promote / demote shard strategy
- threshold changes (if any)
- rationale
```

## Decision logging

Every calibration decision must be logged with:

- country code
- previous and new shard strategy
- previous and new thresholds
- evidence window dates
- approver and rationale

Store decision logs with runbook updates and reference them in release notes for transparency.

Machine-readable contract and example:

- `contracts/schemas/wizard-calibration-decision-log.schema.json`
- `platform-control/tests/fixtures/wizard_calibration_decision_log_example.json`

Validation test:

- `uv run --project platform-control pytest platform-control/tests/unit/test_wizard_calibration_contract.py`

## Related

- `docs/architecture/temporal-argilla-wizard-architecture.md`
- `docs/runbooks/platform-control-multi-country-operator-playbook.md`
- `docs/runbooks/scraping-run-health-dashboard.md`
