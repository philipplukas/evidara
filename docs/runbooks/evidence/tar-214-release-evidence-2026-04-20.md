=== Prod E2E Smoke (2026-04-20) ===

### Health
```json
{"status":"ok","service":"platform-control"}
```
Result: PASS

### Compliance Policies
Count: 2
Result: PASS

### Jurisdictions
Count: 49
Result: PASS

### Authorities
Count: 38
Result: PASS

### Local Test Suites
- vertical-slice-exit-gates-local.sh: PASS (14/14 legal-search, 3/3 platform-control)
- platform-control pytest: 332 passed, 2 skipped
- document-intelligence pytest: 227 passed, 11 skipped, 24 subtests

### CI (GitHub-hosted)
- PR #321 (latest merge): check PASS (2m10s), contract-validation PASS (58s), scraping-qa PASS (18s)
