# Platform-Control Multi-Country Operator Playbook (CH, AT, DE, FR, IT)

Owner: Platform team  
Last reviewed: 2026-04-07  
Last verified: 2026-04-07 (docs metadata and CI runbook lint)  
Applies to: dev, staging, production

## Purpose

Define one operator workflow for onboarding and running sources across five countries with country-specific overlays for jurisdiction mapping, approval checks, and triage.

## Operator outcomes

1. Onboard sources with consistent scope semantics.
2. Approve source versions with explicit country mapping checks.
3. Run and monitor acquisition flows with predictable country overlays.
4. Triage failures using a shared decision path.

## Shared operator flow

```text
1. Select country overlay (CH/AT/DE/FR/IT)
2. Create source with normalized scope metadata
3. Create/update source version acquisition config
4. Run pre-approval checklist
5. Approve source version
6. Trigger run (preview or production)
7. Monitor run status + downstream DI signals
8. Execute triage path if failures occur
```

## Country overlay matrix

| Country | Scope emphasis | Approval hotspot | Run monitoring hotspot | Typical triage hotspot |
|---|---|---|---|---|
| CH | federal vs canton mapping | jurisdiction key consistency | canton distribution in output | canton metadata normalization |
| AT | national authority taxonomy | authority-type correctness | decision/commentary separation | source-family misclassification |
| DE | federal vs Länder scope | Länder coverage declaration | state-level output spread | jurisdiction alias drift |
| FR | judicial vs administrative channels | source-family split validation | court-channel distribution | court-level mapping mismatch |
| IT | national + locality context | court-level metadata quality | decision metadata completeness | sparse authority metadata |

## Country complexity research summary

The five-country rollout has meaningful hierarchy variation and should not use one fixed shard granularity.

### Complexity signals to model

- **Hierarchy depth variance:** CH and DE often require deeper effective traversal due to federal/subnational structures.
- **Breadth variance:** DE and CH can create high parallel jurisdiction breadth.
- **Dual-order/circuit variance:** FR and IT have strong administrative/specialized branches that can change authority mapping behavior.
- **Language variance:** CH has multi-language operational pressure relative to other target countries.
- **Metadata quality variance:** IT and mixed-source cohorts can require stronger review routing.

### Operational implication

- Maintain one shared wizard state machine across countries.
- Tune shard granularity and review thresholds per country profile:
  - high complexity -> `country + jurisdiction + authority`
  - medium complexity -> `country + jurisdiction`
  - low complexity -> `country` only

Reference artifacts:

- `platform-control/tests/fixtures/wizard_country_hierarchy_profiles.json`
- `platform-control/tests/unit/test_wizard_country_profiles.py`
- `docs/runbooks/multi-country-wizard-calibration-worksheet.md`

## Approval checklist (required for all countries)

- [ ] `jurisdiction` mapping aligns to canonical keys.
- [ ] `source_family` mapping aligns to canonical set (`law`, `decision`, `commentary`, `administrative_guidance`).
- [ ] `language` defaults and expected alternates are declared.
- [ ] `authority_type` and `court_level` mapping examples are validated.
- [ ] Preview run produces artifacts with expected country distribution.
- [ ] Discovery drift report is reviewed (accepted/rejected with rationale).
- [ ] No country-specific custom key introduced without contract review.

## Country-specific checklist add-ons

### CH

- [ ] Canton aliases resolved to approved jurisdiction terms.
- [ ] Federal and canton content are distinguishable in metadata.

### AT

- [ ] National authority identifiers map to approved authority taxonomy.
- [ ] Decision/commentary boundaries reviewed in sample outputs.

### DE

- [ ] Länder labels normalized to canonical jurisdiction keys.
- [ ] Federal and Länder documents coexist without duplicate label variants.

### FR

- [ ] Judicial vs administrative source-family mapping is explicit.
- [ ] Court hierarchy labels map cleanly to `court_level`.

### IT

- [ ] Court metadata completeness threshold met in preview sample.
- [ ] Locality-sensitive metadata does not override canonical jurisdiction semantics.

## Triage decision path

```text
Failure observed
→ Is run execution failing? (provider/connectivity)
  → yes: connector/provider triage
  → no: continue
→ Is content mapping failing? (jurisdiction/source_family/court_level)
  → yes: country overlay mapping triage
  → no: continue
→ Is downstream projection/search inconsistent?
  → yes: legal-search parity and projection history checks
  → no: treat as transient and retry with evidence capture
```

## Triage actions by failure class

| Failure class | First action | Evidence to capture | Escalation owner |
|---|---|---|---|
| Provider execution | inspect run/provider-job status and callback logs | run ID, provider job IDs, raw callback payloads | platform-control |
| Mapping drift | compare source output vs canonical taxonomy keys and review drift artifact candidates | sample artifacts, mapping table diff, rejected keys, candidate patch artifact | platform-control + contracts |
| Projection mismatch | verify processed events and projection ingest order | event IDs, manifest refs, projection history snapshot | legal-search |
| Language/translation mismatch | verify declared source language and UI expectations | language facets, translation indicator behavior, sample docs | legal-search |

## Discovery drift review workflow

1. Run completes and publishes normal acquisition artifacts.
2. Discovery drift artifact is generated for unmapped aliases/labels/language-pairs.
3. Operator reviews each candidate and marks it accepted or rejected with rationale.
4. Accepted changes are applied via reviewed overlay/config update (not runtime mutation).
5. Follow-up run verifies that previous drift items are now mapped.

## Acceptance gates for operator readiness

- Country overlay checklist passes for each target country.
- One successful preview and one successful production run per country.
- At least one simulated failure triaged using this shared playbook per country.
- No unresolved taxonomy key drift in approval artifacts.
