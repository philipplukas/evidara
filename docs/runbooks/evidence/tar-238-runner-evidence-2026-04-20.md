=== Runner State (2026-04-20) ===

**GitHub-hosted runners (ubuntu-latest):** HEALTHY
- Root cause of 2026-04-20 fast-fail: GitHub Actions billing (payment failure)
- Fix: billing updated, all ubuntu-latest jobs running normally
- Evidence: PR #320 — check (2m13s), contract-validation (58s), scraping-qa (18s) all pass
- Evidence: PR #321 — check (2m10s), contract-validation (58s), scraping-qa (18s) all pass

**Self-hosted runners (ARC/Hetzner):**
- Heavy pool: 2 runners OFFLINE (evidara-heavy-v2-nsm2c-runner-{qds9p,wn8gg})
- Light pool: 1 runner ONLINE but labels=[] (evidara-light-qnpld-runner-s799c)
- Impact: image builds (runtime-images.yml) queue indefinitely
- Mitigation: PR #303 routed document-service to evidara-heavy; Cloud Build used for manual deploys

**Assessment:** GitHub-hosted CI is fully reliable. Self-hosted pool needs ARC recycle.
The self-hosted pool is only used for Docker image builds, not for test/check workflows.
All code quality gates (check, contract-validation, scraping-qa, check-title) run on GitHub-hosted.
