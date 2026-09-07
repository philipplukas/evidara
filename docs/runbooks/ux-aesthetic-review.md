# UX / Aesthetic review runbook

Owner: Design / frontend
Last reviewed: 2026-09-07
Last verified: 2026-09-07 (operator-panel walkthrough — #928, #929, #930)
Applies to: legal-search/frontend, platform-control/admin

A reusable checklist for periodically auditing the visual and interaction
quality of Evidara's two user-facing surfaces:

- `legal-search/frontend` — operator and end-user search experience (Next.js, Tailwind, design tokens).
- `platform-control/admin` — operator control plane (Next.js, `ra-core` + Tailwind
  primitives; ADR-0026 retired MUI from the v2 pages, so §6's older findings
  describe a UI that no longer exists).

This runbook is meant to be run every release milestone or before any
externally-shared demo, and captures both the evidence-gathering workflow
and a concrete list of issues found so far.

---

## 1. Scope and cadence

- Run this review **at least once per milestone** and any time the design
  system (ADR-0016) or a shared primitive changes.
- Two deliverables per run:
  1. An updated screenshot pack in `legal-search/frontend/screenshot-pack/`.
  2. **GitHub issues** — one per independently schedulable change, plus a meta
     issue carrying the method, what was confirmed working, and what was
     discarded. Findings do not go in `docs/`: a findings file goes stale exactly
     the way §2 of this runbook did, whereas an issue gets closed.

## 2. Prerequisites

**Bring-up lives in [`.claude/skills/run-admin-panel/SKILL.md`](../../.claude/skills/run-admin-panel/SKILL.md),
not here.** That file is maintained against the running stack; this section
records only what a *reviewer* has to know, and defers to it for the commands.

- **npm, per surface. Not pnpm.** There is no `pnpm-lock.yaml`; the repo is not a
  workspace and each JS surface owns its own `node_modules` (AGENTS.md). CI
  installs with `npm ci` inside each surface.
- **Node 22 via nvm** — `source ~/.config/nvm/nvm.sh; nvm use`. System node breaks
  the build and makes gates dishonest.
- Ports: legal-search frontend **3101**, admin dev server **3000**. The compose
  production build of the admin is **3100** — reading the stale one is the usual
  reason "my change did not show up".

### The two traps that produce a dishonest review

Both fail *quietly*, into a panel that looks empty rather than broken. A review
that hits either is reviewing nothing.

1. **API auth fails closed.** Without
   `PLATFORM_CONTROL_AUTH_DEV_ALLOW_UNAUTHENTICATED=1` every protected route
   answers **503** and every list renders empty. `/health` stays 200 and will not
   reveal it. Probe a protected route and require 200:

   ```bash
   curl -s -o /dev/null -w '%{http_code}\n' \
     'http://127.0.0.1:8000/v1/reference-data/jurisdictions?limit=1'
   ```

2. **Every locally-acquired run ends `completed`.** So `pending`, `running`,
   `failed` and `cancelled` have never existed on a developer machine — the
   attention chip, cancel, retry, the failure copy and four of five preset chips
   render nothing. Seed them first:

   ```bash
   bash scripts/platform-control-demo.sh seed-demo-runs
   ```

   **A review that never saw the populated states is not a review.** Reviewing
   empty states as though they were the product is how a UX pass produces
   confident nonsense.

- **Drive with Playwright, not the Chrome extension.** The Next 16 dev server
  never reports `document_idle`, so extension-based automation times out. This is
  about the extension, not automation generally — Playwright against `npm run dev`
  is the fast path and needs no production build.

## 3. Evidence-gathering workflow

### 3.1 Screenshot pack (automated)

```bash
cd legal-search/frontend
NEXT_PUBLIC_USER_ROLE=admin \
NEXT_PUBLIC_ADMIN_ALLOWED_ROLES=admin \
npm run e2e:screenshot-pack
```

Produces 23 canonical PNGs in `legal-search/frontend/screenshot-pack/`:

- `cross-surface-header-navigation.png`
- `legal-search-result-list.png`
- `legal-search-detail-panel.png`
- `legal-search-filter-panel-populated.png`
- `detail-tab-details.png`, `detail-tab-related.png`, `detail-tab-references.png`
- `admin-dashboard.png`, `admin-run-launch-preflight.png`,
  `admin-run-lifecycle-visibility.png`, `admin-source-detail.png`
- `mobile-search-home.png`, `mobile-result-list.png`, `mobile-detail-sheet.png`
- **Pass 4 graduation:** `admin-sources-list-v2.png`, `admin-source-detail-v2.png`,
  `admin-runs-list-v2.png`, `admin-run-detail-v2.png`,
  `admin-authority-create-v2.png`, `admin-authority-edit-v2.png`,
  `admin-jurisdiction-create-v2.png`, `admin-jurisdiction-edit-v2.png`,
  `admin-source-create-v2.png` — Tailwind + `ra-core` ports using the
  graduated primitives in `platform-control/admin/src/ui/primitives/`.
  Pass 4 diff review concluded on 2026-04-18; see ADR-0026.
  ADR-0026 phase P2 (Select primitive + SourceCreateV2) adds
  `admin-source-create-v2.png`; the `Select` primitive (radix-ui under
  `useInput`) graduates alongside it and powers the jurisdiction /
  authority pickers on the v2 page.

The spec hides Next.js dev indicators and TanStack Query devtools by stripping
the corresponding shadow-DOM hosts before each screenshot — confirm none bleed
into the pack.

**If you write your own capture driver, you must strip them too.** The 2026-09-07
walkthrough used a custom driver, did not, and nearly filed the circular "N"
badge as a misplaced avatar in the admin sidebar. It is `nextjs-portal` /
`next-dev-overlay`, it lives in shadow DOM so CSS alone cannot reach it, and it
does not exist in a production build. See M-3b in §6 — this was already known,
and knowing it was in a runbook nobody read is the reason for §2's first line.

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

### 4.1 The operator questions

The criteria above are about how a screen *looks*. These are about whether it
*works*, and the 2026-09-07 pass found more with them than with anything else.
Apply all six to every view so findings are comparable rather than a pile of
opinions.

1. **Does it answer the question the operator arrived with?** Or is the answer
   only derivable by opening three accordions, or on page 30 of 44?
2. **Is anything shown that cannot be acted on, or actionable but not shown?**
   The dashboard leading with a *cancelled* run (#932) is the canonical case.
3. **Empty vs unknown vs zero.** This repo's deepest rule. A blank cell that
   means "unknown" is the defect the coverage ledger exists to prevent — and a
   count that is really a page size is the same defect (#934).
4. **Is every control reachable at 1280px** without knowing to scroll?
5. **Does it contradict another screen — or itself?** A run detail stating
   "Captured 944" and "50 rows" for one quantity is a contradiction inside one
   viewport.
6. **Light and dark, every view.** Dark mode shipped in #873 with almost no
   coverage.

### 4.2 What counts as a finding

Two rules, both earned the hard way on 2026-09-07:

- **Every finding carries a `file:line` or a measured value.** A finding with
  neither does not get filed. Two candidates were discarded on this rule that
  pass — one was the Next.js dev badge, one was the reviewer's own capture driver
  using a path where the app uses a hash route.
- **Every "X is missing" is resolved against
  [`contracts/api/platform-control.openapi.yaml`](../../contracts/api/platform-control.openapi.yaml)
  to *unrendered* (the data exists and the panel ignores it) or *unavailable* (no
  server capability), never left ambiguous.** They have very different costs, and
  conflating them produces work nobody can schedule. One finding in that pass
  changed category *the same day*, because the endpoint it needed had just
  merged.

## 5. Accessibility spot-check

- Keyboard: tab through a full operator journey; focus ring visible and
  consistent on every interactive element.
- Touch: primary interactive elements ≥ 44×44 on mobile viewports.
- Contrast: WCAG AA (4.5:1 body, 3:1 large text) — spot-check any new colour
  pair introduced since last review.
- i18n: toggle DE ↔ FR on legal-search; no layout breakage, no untranslated
  keys.

## 6. Findings log — historical

**This is an archive, not a checklist.** Everything below is fixed, and the
entries from Passes 1–4 describe the MUI-era admin that ADR-0026 retired — the
component names in their resolutions largely no longer exist.

It is kept because the *findings* still teach (M-3b in particular, which the
2026-09-07 pass rediscovered the hard way), and deliberately separated from the
method above, because the two age at different rates: that is why §2 of this
runbook went stale for five months while §4 stayed usable.

Current findings live in GitHub issues — see §1.

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

#### Pass 4 — open

| ID | Sev | Finding | Status |
|----|-----|---------|--------|
| UX-12 | Normal | Pass 4 spike ships six Tailwind + `ra-core` ports alongside the MUI versions: sources list (`/sources-v2`), sources show (`/sources-v2/:id`), runs list (`/runs-v2`), runs show (`/runs-v2/:id`), authority create (`/authorities-v2/create`), authority edit (`/authorities-v2/:id/edit`). The matrix covers list / detail / filter / create / edit + a large detail page (`RunShowV2`) with derived content (decision-support 2×2, duration compute), exercising `useListController`, `useShowController`, `useGetMany`, `useGetOne`, `Form`, `useInput`, `useCreateController`, `useEditController`, and `useNotify` with zero MUI primitives. Captures: `admin-sources-list-v2.png`, `admin-source-detail-v2.png`, `admin-runs-list-v2.png`, `admin-run-detail-v2.png`, `admin-authority-create-v2.png`, `admin-authority-edit-v2.png`. ADR-0026 P3 (2026-04-18) added `<Accordion>` and ported `RunDetailSections` to `RunDetailSectionsV2` (Pipeline Health banner + 5 collapsed accordion sections bound to `useGetList`); it now renders inside `RunShowV2` and is no longer deferred. | **Review** — diff the v1/v2 pairs, decide graduate-to-`@evidara/ui` vs. discard. Deferred from the spike (all intentional, all listed as follow-up increments): bulk selection, MUI `SelectInput` (jurisdiction dropdown), source-versions section, handoff panel, run mutations (`CancelRunButton`, `RunLaunchButton`), keyboard shortcuts, scope/slug-change alerts. See header comments in `SourceListV2.tsx`, `SourceShowV2.tsx`, `RunListV2.tsx`, `RunShowV2.tsx`, `AuthorityCreateV2.tsx`, `AuthorityEditV2.tsx`, `AuthorityFormV2.tsx`, and `src/ui/primitives/`. Notifications still render via the MUI shell's `<Notification>` — intentional coexistence until the shell ports. |

*All Pass 3 findings were resolved in the previous batch.*

#### UX-12 — Pass 4 outcome (2026-04-18)

Pass 4 concluded **proceed with graduation**. Primitives moved from
`platform-control/admin/src/resources/sources/_spike/` to
`platform-control/admin/src/ui/primitives/`; `Spike*` prefixes dropped;
`TextField` renamed to `TextInput` (matches ra-core naming). V2 pages
keep the `V2` suffix and coexist with MUI originals until they reach
parity (per ADR-0026 migration phases). A second form pair —
`JurisdictionCreateV2` / `JurisdictionEditV2` — shipped alongside the
graduation because it's a trivial pattern copy of the authority form.

#### UX-12 sub-findings (from first visual pass, 2026-04-18)

Structured findings from the first side-by-side review of the v1/v2 pack.
Resolve inside `_spike/*` (or the v2 page files) and re-capture before
promoting to `@evidara/ui`. All "proceed-with-graduation" severity —
none are architectural.

| ID | Sev | Finding | Action |
|----|-----|---------|--------|
| UX-12.1 | Low | v2 card elevation was sharper than v1: spike primitives hard-coded `0_18px_44px_rgba(29,41,61,0.06)` while MUI used a different `SHADOW_CARD`. | **Fixed (2026-04-18).** Promoted both `--shadow-card` and `--shadow-card-hover` to CSS custom properties in `globals.css`; `designTokens.ts` now exports them as `var(...)` strings so MUI theme and Tailwind utilities read from a single source. All v2 primitives use `shadow-[var(--shadow-card)]`. |
| UX-12.2 | Low | "Deferred in this spike" aside on `/sources-v2/:id` and `/runs-v2/:id` was prominent enough to be read as immaturity rather than intentional deferral. | **Fixed (2026-04-18).** Reworked as a compact footnote: smaller radius, lighter dashed border, 11px text, single-paragraph summary instead of bulleted list. Still visible but reads as a footnote rather than a card. |
| UX-12.3 | Normal | Runs list v2 drops the gradient hero panel that v1 uses to onboard operators ("Task-led run operations" + keyboard-shortcut hint). | **Open** — design call, not a defect: re-add as a compact banner component if operator onboarding matters; keep dropped for power-user density. |
| UX-12.4 | Low | "Active" status pill appeared twice on v2 source-show (header + lifecycle card). | **Fixed (2026-04-18).** Dropped the pill from the lifecycle card; kept it in the header. Card keeps its heading, description, and status-detail copy so the contextual meaning isn't lost. |
| UX-12.5 | Normal | MUI shell chrome is subtitle-mismatched on v2 pages (`Source lifecycle, approval state, and run operations.` shows on `/runs-v2` and `/authorities-v2/*`). | **Open** — pre-existing chrome bug exposed by v2; fixes when the shell migrates. Track here so it's not silently carried forward. |

#### Stream G kickoff — UI/UX aesthetics, styling, and brand consistency (2026-04-27)

This pass is the evidence log for
[Stream G](../process/design-system-parallel-plan.md#stream-g-uiux-aesthetics-styling-and-brand-consistency)
under TAR-243. Treat it as a visual-quality lane, not a contract or backend
lane.

| ID | Sev | Finding / scope | Action |
|----|-----|-----------------|--------|
| UX-13 | Normal | Legal-search shell polish needs a token hygiene pass before deeper layout work. Hardcoded workspace-shell color literals make the page chrome harder to align with ADR-0027 shared brand tokens. | **Started (2026-04-27).** Move workspace shell color treatments into local `globals.css` variables, then continue with header / results / detail / filters polish in surface-scoped PRs. |
| UX-14 | Normal | The older five visual Linear streams overlap TAR-243 but are not yet explicitly folded into the design-system plan. | Fold into Stream G as implementation lanes: visual regression, Kontrollbereich hierarchy, result scope/relevance copy, detail/filter/loading parity, and admin readiness/version actions. |
| UX-15 | Low | Screenshot baseline updates can become noisy if mixed with unrelated style fixes. | Keep screenshot-pack or visual-baseline refreshes in a dedicated follow-up PR unless a changed baseline is the direct acceptance evidence for the same styling PR. |
| UX-16 | Normal | Admin must look like the same Evidara product as legal-search without copying the research workspace's document-reading density. | **Started (2026-04-27).** Stream G3 now covers shell tokenization, primitive token parity, and first screen-polish pass. Shared semantics: navy identity chrome, violet action/active states, matching focus rings, status colors, pill semantics, and elevation tokens. Intentional difference: admin keeps denser tables, task-first headers, and operator scanning layouts. |

##### Stream G3 admin PR slices

1. **Shell tokenization.** `globals.css`, `AppBar`, `AppShell`, `SidebarMenu`, shell token tests. Serializes on `platform-control/admin/src/app/globals.css`. Completed for the admin shell in this pass, including a guard against returning shell controls to the older brand-specific focus token. Follow-up visual review removed default link underlines, renamed the operator surface to `Preview approvals`, and fixed v2 create-route title / active-nav matching.
2. **Primitive parity.** `Button`, `Pill`, `Toast`, `DataTable`, `TextInput` / `Select`; add token/class tests. Serializes on shared admin primitives. Completed first pass using shared accent, focus, status, surface, and border tokens.
3. **Screen polish.** Dashboard/source-health plus v2 source/run/reference-data screens; remove prototype copy, keep admin headings sans-first, normalize table/header/form surfaces. Completed first pass for dashboard, source health, source v2, run v2, source-create, authority-create/edit, and jurisdiction-create/edit screens.
4. **Evidence/docs.** Screenshot-pack refresh and TAR-243 runbook update. Screenshot pack passed locally on 2026-04-27; screenshot files are generated evidence artifacts and are not tracked in this repo state.

##### Stream G4 Tailwind migration checkpoint

The first post-merge MUI-reduction slice ports the admin dashboard's read-only
chrome to Tailwind primitives: command cards, stat cards, source health,
recent runs, and correction metrics now render via `Panel`, `DataTable`,
`Pill`, `InlineAlert`, and `Spinner`. Shared status-level helpers moved out of
the MUI `StatusBadge` module so v2 Tailwind pages can consume status semantics
without importing MUI chip/icon code. The run-launch dialog internals remain
MUI for now, but the dashboard trigger uses the shared Tailwind `Button`.

The **sources** resource has since completed ADR-0026 phase P5 (#501): the
MUI `SourceList` / `SourceShow` / `SourceCreate` / `SourceVersionsSection`
files were deleted and their Tailwind ports renamed into the canonical
`/sources`, `/sources/create`, `/sources/:id/show` routes, wired through
`<Resource list/create/show>` (no more `/sources-v2` `<CustomRoutes>`). The
Pass 4 UX-12 entries above that reference `SourceListV2.tsx` / `SourceShowV2.tsx`
/ `/sources-v2` are point-in-time spike records; the live files are now
`SourceList.tsx` / `SourceShow.tsx` / `SourceCreate.tsx` /
`SourceVersionsSection.tsx`. Runs + reference-data resources remain in the
coexistence window at their `/*-v2` routes.

## 7. Where findings go

**GitHub issues.** Linear is no longer where this repo tracks work; the sections
this replaced described a Linear epic (TAR-243), a free-tier `save_issue` limit,
and six child-issue templates, none of which apply.

Shape that worked on 2026-09-07 (#928 / #929 / #930 / #931):

- **One issue per independently schedulable change.** Split along the lane lines
  in the lane map, not along the order you happened to find things in.
- **Bundle findings that share a lane** when that lane is serial inside itself —
  four separate admin issues would be worked one after another anyway, and one PR
  beats four contending on the same visual baseline.
- **Record what you discarded**, in the issue, with the reason. Not filing
  something is part of the evidence that the pass was careful, and it stops the
  next reviewer re-finding it.
- **Say what was NOT reviewed.** A view seen in one theme, or in an empty state
  only, is *partially reviewed* — not passed. The 2026-09-07 pass could not
  review Corrections beyond its empty state because the local stack had none,
  and said so.

## 8. Related artifacts

- `legal-search/frontend/e2e/screenshot-pack.spec.ts` — source of truth for
  screenshot evidence.
- `legal-search/frontend/docs/design-system.md` — design tokens, primitives.
- `platform-control/admin/docs/status-level-vocabulary.md` — status colour
  semantics.
- ADR-0016 — design system contracts.
- Cursor canvas: `ux-aesthetic-review.canvas.tsx` — interactive visual review.
