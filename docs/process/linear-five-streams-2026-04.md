# Linear update — five parallel streams (started)

Paste the block below as a **comment** on your parent epic, or create **five sub-issues** (one title + description each).

---

## Stream 1 — Visual regression CI gate

**Status:** Ready — Linux baselines exist and the `frontend-visual-regression`
job is enabled in `.github/workflows/legal-search.yml`.

**Done when:**

- `npm run e2e:visual` passes locally and on `ubuntu-latest` in CI.
- `scripts/playwright-visual-update-docker.sh` documented in `legal-search/frontend/docs/testing-matrix.md` (or runbook).
- Baseline updates are a deliberate PR step (`npm run e2e:visual:update`).

**Links:** `legal-search/frontend/e2e/visual.spec.ts`, `.github/workflows/legal-search.yml` (job `frontend-visual-regression`).

---

## Stream 2 — Kontrollbereich hierarchy (legal-search)

**Status:** In progress — **mobile-first quieter styling** (muted chip on small viewports, brand accent from `lg`); semantics doc still recommended.

**Done when:** Product decision (toggle vs destination) recorded; mobile strip no longer reads as primary CTA; desktop aligned with nav weight.

**Links:** `AppHeader.tsx`, `globals.css` (`.app-header__control-plane`).

---

## Stream 3 — Results scope copy + relevance (legal-search)

**Status:** In progress — **source type tabs i18n** (DE `Alle` / `Urteile` / …, FR `Tout` / …); **relevance pill** uses `results.list` strings + **tooltip** clarifying algorithmic sort (not manual verification).

**Done when:** No ambiguous two-letter scope chips in DE; copy matches legal claim.

**Links:** `ContextBar.tsx`, `ResultList.tsx`, `de.json` / `fr.json` (`results.sourceTypes`, `results.list`).

---

## Stream 4 — Detail + filters + loading parity

**Status:** In progress — **detail tab** inactive/active contrast; **route `loading.tsx`** single-column below `lg`; **Filters sheet** footer `RESET_ALL` + localized title.

**Done when:** Desktop tab states visibly distinct; mobile skeleton matches loaded shell; sheet offers full reset like `ContextBar`.

**Links:** `DetailTabs.tsx`, `loading.tsx`, `FiltersSheet.tsx`.

---

## Stream 5 — Admin readiness + version actions

**Status:** In progress — **readiness strings** centralized in `readiness-messages.ts`; **version status** uses `StatusBadge` + icons; **Preview / Production** separated with divider + explicit Preview `color`.

**Done when:** New readiness codes only touch one module; production launch still confirm-gated; table status not colour-only.

**Links:** `platform-control/admin/src/lib/admin/readiness-messages.ts`, `RunLaunchDialog.tsx`, `SourceVersionsSection.tsx`, `StatusBadge.tsx` (`sourceVersionStatusToLevel`).

---

**Note:** I do not have Linear API access from this environment — paste the sections above into Linear manually.
