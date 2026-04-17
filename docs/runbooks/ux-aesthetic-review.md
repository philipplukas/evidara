# UX / Aesthetic review runbook

Owner: Design / frontend
Last reviewed: 2026-04-16
Last verified: 2026-04-16 (Pass 3, commit 78ee96b)
Applies to: legal-search/frontend, platform-control/admin

A reusable checklist for periodically auditing the visual and interaction
quality of Evidara's two user-facing surfaces:

- `legal-search/frontend` — operator and end-user search experience (Next.js, Tailwind, design tokens).
- `platform-control/admin` — operator control plane (Next.js, react-admin, MUI).

This runbook is meant to be run every release milestone or before any
externally-shared demo, and captures both the evidence-gathering workflow
and a concrete list of issues found so far.

---

## 1. Scope and cadence

- Run this review **at least once per milestone** and any time the design
  system (ADR-0016) or a shared primitive changes.
- Two deliverables per run:
  1. An updated screenshot pack in `legal-search/frontend/screenshot-pack/`.
  2. A review pass (markdown comment + Linear sync) recording findings and
     severity.

## 2. Prerequisites

- Local stack healthy: `legal-search` on port **3101**, `admin` on port **3100**.
  The admin dev server requires:

  ```bash
  NEXT_PUBLIC_USER_ROLE=admin \
  NEXT_PUBLIC_ADMIN_ALLOWED_ROLES=admin \
  pnpm --filter admin dev
  ```

- Playwright dependencies installed (`pnpm --filter frontend exec playwright install`).
- Linear access via the `plugin-linear-linear` MCP (or CLI equivalent) for
  sync. Note the workspace has been hitting free-tier `save_issue` limits —
  fall back to a `save_comment` payload when that happens.

## 3. Evidence-gathering workflow

### 3.1 Screenshot pack (automated)

```bash
cd legal-search/frontend
NEXT_PUBLIC_USER_ROLE=admin \
NEXT_PUBLIC_ADMIN_ALLOWED_ROLES=admin \
pnpm exec playwright test e2e/screenshot-pack.spec.ts --reporter=list
```

Produces 14 canonical PNGs in `legal-search/frontend/screenshot-pack/`:

- `cross-surface-header-navigation.png`
- `legal-search-result-list.png`
- `legal-search-detail-panel.png`
- `legal-search-filter-panel-populated.png`
- `detail-tab-details.png`, `detail-tab-related.png`, `detail-tab-references.png`
- `admin-dashboard.png`, `admin-run-launch-preflight.png`,
  `admin-run-lifecycle-visibility.png`, `admin-source-detail.png`
- `mobile-search-home.png`, `mobile-result-list.png`, `mobile-detail-sheet.png`

The spec hides Next.js dev indicators and TanStack Query devtools by stripping
the corresponding shadow-DOM hosts before each screenshot — confirm none bleed
into the pack.

### 3.2 Live walkthrough (manual)

Open both apps and walk through the operator journey:

1. Legal-search: landing → search → filter → detail panel → detail tabs → mobile.
2. Admin: dashboard → sources list → source detail → runs list → run detail →
   run launch preflight → cross-surface "Back to legal search".

## 4. Review criteria

For each screenshot or screen, rate the following on a 1–5 scale and note
concrete findings:

- **Hierarchy.** Is the most important element visually dominant? Do heading
  levels, small-cap labels, and metadata cascade sensibly?
- **Rhythm & spacing.** Consistent use of the spacing scale; no cramped or
  yawning gaps; alignment to a shared grid.
- **Color semantics.** Status colours (success / warning / error / info)
  match the vocabulary in
  `platform-control/admin/docs/status-level-vocabulary.md` and don't bleed
  into non-status usage (e.g. red used for a content-type badge).
- **Cross-surface coherence.** Shared primitives (badges, buttons, cards,
  tabs) render identically across surfaces under the same semantic state.
- **Information density.** No raw field/value dumps; long pages use
  progressive disclosure (collapsible accordions, tabs) so first-screen
  content answers the operator's first question.
- **Dev-chrome hygiene.** No floating dev widgets, overlays, or fixed
  high-z-index elements in the screenshot pack.

## 5. Accessibility spot-check

- Keyboard: tab through a full operator journey; focus ring visible and
  consistent on every interactive element.
- Touch: primary interactive elements ≥ 44×44 on mobile viewports.
- Contrast: WCAG AA (4.5:1 body, 3:1 large text) — spot-check any new colour
  pair introduced since last review.
- i18n: toggle DE ↔ FR on legal-search; no layout breakage, no untranslated
  keys.

## 6. Findings log

Severity scale: **Critical** (blocks release) / **High** / **Medium** / **Low**.

### 6.1 Fixed (carried through Pass 1–3)

| ID | Sev | Finding | Resolution |
|----|-----|---------|------------|
| M-1 | High | Duplicate `AUSGANGSSUCHE` breadcrumb rows on every result view | Removed duplicate `<ResultSetScopeBar />` from `WorkspaceClient.tsx`. |
| M-2 | Low | Three detail-tab screenshots were indistinguishable | Screenshot pack now clicks the actual tab triggers in-session, force-expands the `react-resizable-panels` detail panel to ≈40%, and waits for content. Mock data fields (`label`) corrected. |
| M-3 | Medium | Palm-tree / island widget artifact on every legal-search screenshot | Stripped via `hideDevToolWidgets()` CSS injection. |
| M-3b | Low | Circular "N" (Next.js dev) badge on every legal-search screenshot | Shadow-DOM host (`nextjs-portal`, `next-dev-overlay`) is removed via `page.evaluate()` — CSS alone couldn't reach it. |
| M-4 | High | Mobile filter area consumed ≈40% of viewport | `ContextBar.tsx` now collapses filters behind a single "Filter N" chip on mobile. |
| M-5 | Medium | Mobile toolbar wrapped `Kontrollbereich` to a second line | `globals.css` `.app-header__nav` uses `overflow-x-auto` below 480px; secondary copy hidden. |
| M-7 | Critical | Admin run-lifecycle page stacked everything at once | `RunDetailSections.tsx` wraps Provider Jobs / Captured Resources / Raw Artifacts / DI Processing Status / Document Lifecycle in MUI `Accordion` (collapsed by default, with item counts). Pipeline Health stays expanded. |
| M-8 | Medium | Pipeline Health chip row overload | Consolidated event counts into a single compact `Typography`. |
| M-9 | Medium | Source detail metadata wasted horizontal space | Swapped `SimpleShowLayout` for a 2-column MUI `Grid`. |
| M-10 | Low | Source Versions table only had one row in screenshots | Mock now returns 3 rows (`approved` / `pending_approval` / `draft`). |
| M-11 | Medium | `cross-surface-header-navigation.png`, `legal-search-result-list.png`, `mobile-search-home.png` showed loading skeletons | Spec performs the search and waits for `article` before those captures. |
| UX-5 | Low | Acquisition config rendered as unreadable inline JSON | `SourceVersionsSection.tsx` renders it as compact monospace `<pre>`. |
| UX-6 | Low | Two prominent uppercase chips in admin header ("Control plane" / "Operator only") | Replaced with a single subtle "Operator · Control plane" chip. |
| M-14 | Medium | Admin sidebar's first nav item ("Dashboard") clipped behind the top app bar | Scoped `.RaSidebar-paper` / `.RaLayout-sidebar .MuiDrawer-paper` selector with `paddingTop: 72/80px` and a separate `.RaSidebar-fixed { height: 100%; minHeight: 0 }` rule in `AdminApp.tsx` so the drawer content clears the bar without overflowing. |
| M-15 | High | Admin run-lifecycle page had a raw unformatted field/value dump between "Stage summary" and "Lifecycle sections" | `RunShow.tsx` replaces the `SimpleShowLayout` stack of 13 fields with a 2-col MUI `Grid` + `RunFieldCell` helper mirroring the M-9 pattern on sources. |
| UX-9 | High | Detail panel opened as a narrow sliver on desktop | `WorkspaceClient.tsx` uses imperative `rightRef.current?.resize(32)` (not `expand()`) plus `defaultSize={isDetailOpen ? 32 : 0}` so the panel lands inside `[minSize=25, maxSize=45]` on first paint. Center panel rebalanced (50 / 78). Screenshot pack retains a lightweight `forceExpandDetailPanel` helper as defensive insurance for headless Playwright only. |
| UX-10 | Low | "Back to legal search" only visible as a small top-right button | `AdminApp.tsx` now ships a custom `EvidaraAdminMenu` passed via `<Layout menu>` that renders react-admin's default `<Menu />` plus a persistent footer `ListItemButton` ("Back to legal search" / "Return to active search", `ArrowBackIcon`) docked via `mt: auto`. |
| M-16 | Medium | Admin source detail 2-col grid was spatially correct but field labels were missing | `SourceShow.tsx` now wraps each grid cell in a local `SourceFieldCell` helper (MUI `Typography variant="overline"` above the value) mirroring the M-15 `RunFieldCell` pattern. Labels visible: SOURCE ID, NAME, DESCRIPTION, JURISDICTION, AUTHORITY, DOCUMENT FAMILY, SOURCE TYPE, CREATED, UPDATED. |
| UX-4 | Normal | Badge / pill visual language differed across surfaces (MUI chips vs Tailwind pills) | New "Pill / Badge contract" section in `design-system.md` documents the three pill families (domain colour badge / semantic status badge / neutral metadata chip) with shared visual contract (`borderRadius: 999`, 11px text, weight 600, 24px at `size="small"`). `AdminApp.tsx` `MuiChip` theme aligned: full-pill radius, 11px, weight 600, small-size 24px height. `status-level-vocabulary.md` cross-references the new section. |
| UX-7 | Low | `COURT DECISION` badge red/pink fill + cross icon read as error | `badge-tokens.ts` retuned the `pink` key from fuchsia (`#fce7f3` / `#9d174d`) to sky (`#e0f2fe` / `#075985`) — 8.1:1 contrast, institutional rather than destructive. Key name kept for BFF backwards compatibility. Unit test in `__tests__/badge-tokens.test.ts` updated. |
| UX-8 | Low | Result card action buttons (`Anheften`, `Open decision`, pivot chips) under 44×44 on mobile | `AccentButton` gets `min-h-11 sm:min-h-0 px-3 py-2 sm:px-2 sm:py-1` — compact on desktop, 44px-floor tap targets on mobile. Pivot chips inside `ResultCard` mirrored the same `min-h-11 sm:min-h-0 py-2 sm:py-1` treatment. |
| UX-11 | Low | Hover / focus ring styles differed between admin (MUI) and legal-search (Tailwind + tokens) | Admin `*:focus-visible` opacity aligned (0.42 → 0.24 to match `--focus-ring`). `MuiButton` + `MuiListItemButton` gained matching `&:focus-visible` outline overrides. `MuiListItemButton` hover tint bumped 5% → 8% to match `--interactive-accent-subtle`. Cross-surface parity paragraph added to `design-system.md §Focus rings`. |

### 6.2 Open

_All Pass 3 findings resolved in this batch. Next review pass will start from a fresh screenshot capture._

## 7. Linear sync — roadmap and templates

Parent epic: **[TAR-243](https://linear.app/tart-baozi/issue/TAR-243)** — _Evidara — Design system & UX (ADR-0016)_.

Status: **In Progress**. Pass 3 sync comment: [`ddc0501b-f27e-4afd-976a-01cf814000ae`](https://linear.app/tart-baozi/issue/TAR-243).

> The workspace is on the Linear free tier and `save_issue` is currently
> rejected with `Usage limit exceeded`. Until that's lifted, the six backlog
> tickets below live as sub-sections of the Pass 3 sync comment and the
> template block below. Promote to real child issues (parent = TAR-243) once
> the workspace is upgraded.

### 7.1 Child-issue templates

All six Pass 3 child issues have been resolved in-process — see §6.1 Fixed for
the resolution notes. The templates below are kept as **reference shape** for
future review passes that may need to open new Linear children under TAR-243.

Each template is structured for Linear's `save_issue`: `team=Tart-baozi`,
`project="Evidara — Design system & UX (ADR-0016)"`, `parentId=TAR-243`,
`labels=["Improvement"]`.

- **UX-N (P#, Sev)** — _Short title._
  One-line scope / acceptance criterion.

### 7.2 Sync checklist per review pass

1. Regenerate the screenshot pack (`playwright test e2e/screenshot-pack.spec.ts`).
2. Diff findings vs the previous pass; update §6 (Findings log) in this file.
3. Update the canvas (`ux-aesthetic-review.canvas.tsx`) if visual artifacts
   need re-linking.
4. Post a `save_comment` on TAR-243 summarising (a) fixed items, (b) still
   open, (c) new findings for the pass.
5. When a child issue closes, move its row from §6.2 Open to §6.1 Fixed with
   a link to the fix PR.

## 8. Related artifacts

- `legal-search/frontend/e2e/screenshot-pack.spec.ts` — source of truth for
  screenshot evidence.
- `legal-search/frontend/docs/design-system.md` — design tokens, primitives.
- `platform-control/admin/docs/status-level-vocabulary.md` — status colour
  semantics.
- ADR-0016 — design system contracts.
- Cursor canvas: `ux-aesthetic-review.canvas.tsx` — interactive visual review.
