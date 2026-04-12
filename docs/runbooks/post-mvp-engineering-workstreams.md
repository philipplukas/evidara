# Post–MVP-path engineering workstreams (Phase 5 memo §7)

Owner: Platform lead  
Last reviewed: 2026-04-11  
Last verified: 2026-04-11  
Applies to: Linear **TAR-66**, **TAR-62**, **TAR-63**, **TAR-67**; starts after **TAR-64** is green per [phase 5 go / no-go memo](phase-5-go-no-go-memo.md) section 7.

This page restates the **recommended sequence** and evidence expectations so engineering planning does not rely only on the memo’s prose.

---

## Dependency rule

Start the numbered stream **after** [Phase 5 evidence checklist](phase-5-evidence-checklist.md) shows **TAR-64** (two dev smokes + Gate D IDs). Until then, prioritize wiring evidence over automating promotion.

**Parallel work:** [TAR-89 workstreams](tar-89-workstreams.md) (metadata credibility) can continue alongside **TAR-66** once **dev** smokes are not firefighting merges (staging optional).

---

## Sequence

| Order | Linear | Focus | Notes |
|------:|--------|-------|-------|
| 1 | **TAR-66** | HTML / ingest hardening | Stability before promotion automation; corpus fixtures |
| 2 | **TAR-62** | DI + infra promotion (dev → staging → prod) | Reduces drift between envs |
| 3 | **TAR-63** | Resumable replay / checkpoints (`platform-control`) | Complements acquisition partial reruns; see `GET /v1/runs/{run_id}` `replay_checkpoint` |
| 4 | **TAR-67** | Operational drills (withdrawal, DLQ, rollback) | Repo runbook sections exist; operators **execute** drills and attach workflow URLs + artifacts per memo §2.1 |

---

## TAR-67 evidence discipline

When filing drill evidence for **TAR-69** / release readiness, use the same pattern across:

- [First vertical slice exit gates](first-vertical-slice-exit-gates.md#drill-evidence-capture-tar-67)
- [DLQ triage and replay](dlq-triage-and-replay.md#operational-drill-evidence-tar-67)
- [Release and rollback](release-rollback.md#operational-drill-evidence-tar-67)
- [Alert response playbook](alert-response-playbook.md#operational-drill-evidence-tar-67)

Prefer **GitHub Actions run URLs** and **downloaded JSON artifacts** over screenshots in git.

---

## Related

- [Phase 5 go / no-go memo](phase-5-go-no-go-memo.md) — gate table, TAR-64 / 77 / 85, section 7 source
- [M5 evidence checklist](m5-evidence-checklist.md) — operator steps including TAR-64 DI Pub/Sub debugging
- [Evidara active parallel PR stacks](../process/evidara-active-parallel-pr-stacks.md) — lane ownership when stacking PRs
