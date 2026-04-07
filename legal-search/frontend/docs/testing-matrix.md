# Testing Matrix

This page is the declarative source of truth for frontend interaction coverage.
It maps each UX journey to the narrowest automated test layer that should own it.

## Current Inventory

| Layer | Existing files | Purpose |
|---|---|---|
| Unit/store | `src/__tests__/workspace.test.tsx`, `src/__tests__/search-constraints.test.tsx`, `src/__tests__/badge-tokens.test.ts` | Reducer transitions, URL-backed constraints state, token mappings |
| Component | `src/__tests__/result-list.test.tsx`, `src/__tests__/result-card.test.tsx`, `src/__tests__/detail-panel.test.tsx` | Render behavior, callback wiring, local interactions |
| Browser e2e | `e2e/smoke.spec.ts`, `e2e/workspace-panels.spec.ts`, `e2e/diagnostic.spec.ts` | End-to-end journeys and panel behavior in real browser |
| CI gate | `.github/workflows/legal-search.yml` | Typecheck/lint/unit/build/contract checks |

## Journey Coverage Matrix

| Journey | Expected state transition | Primary layer | Supporting checks |
|---|---|---|---|
| Search submit | `SEARCH` resets stack and sets `resultSet` | Vitest (`workspace.test.tsx`) | Playwright smoke (`e2e/smoke.spec.ts`) |
| Result focus | `selectedId` URL param set, trail appended | Vitest (`workspace-client.test.tsx`) | Playwright smoke (`e2e/smoke.spec.ts`) |
| Escape close | `selectedId` cleared, detail closes | Vitest (`workspace-client.test.tsx`) | Playwright smoke (`e2e/smoke.spec.ts`) |
| Pivot | `PIVOT` pushes current set to stack | Vitest (`workspace.test.tsx`) | Playwright workspace (`e2e/workspace-panels.spec.ts`) |
| Back navigation | `BACK` pops stack and restores scope | Vitest (`workspace.test.tsx`) | Playwright workspace (`e2e/workspace-panels.spec.ts`) |
| Pin/unpin | `PIN`/`UNPIN` idempotent, header count updates | Vitest (`workspace.test.tsx`, `workspace-client.test.tsx`) | Playwright smoke (`e2e/smoke.spec.ts`) |
| Context constraints | URL-backed filters normalize and persist | Vitest (`search-constraints.test.tsx`) | Component-level context tests as needed |
| Detail tabs and empty state | Route-level rendering and tab affordances | Vitest (`detail-panel.test.tsx`) | Route-level a11y (`workspace-client.a11y.test.tsx`) |
| Panel layout/resizing | Three-panel shell remains operable | Playwright (`e2e/workspace-panels.spec.ts`) | Visual snapshots (`e2e/visual.spec.ts`) |
| Visual theme consistency | Layout and token-driven appearance remain stable | Playwright screenshots (`e2e/visual.spec.ts`) | Badge token unit tests (`badge-tokens.test.ts`) |

## Control Coverage (Button-Level)

| Control surface | Representative controls | Coverage status | Tests |
|---|---|---|---|
| Header | Search submit, Trail/Pinned counters | Covered | `workspace-client.test.tsx`, `smoke.spec.ts` |
| Context bar | Jurisdiction chips, language chips, source type tabs, official toggle | Covered | `interaction-controls.test.tsx`, `search-constraints.test.tsx` |
| Result cards | Focus card, pivot chips, pin action | Covered | `result-card.test.tsx`, `workspace-client.test.tsx`, `smoke.spec.ts` |
| Result scope bar | Back action after pivot | Covered | `interaction-controls.test.tsx`, `workspace.test.tsx` |
| Detail header | Pin toggle, copy citation | Covered | `interaction-controls.test.tsx` |
| Detail tabs | Details/Related/References/Annotation/Structure tab switch | Covered | `detail-panel.test.tsx`, `interaction-controls.test.tsx` |
| Exact-match strip | Exact match quick-select buttons | Covered | `interaction-controls.test.tsx` |
| Filter panel | Dropdown/select, toggles, checkboxes/chips, clear/reset actions | Covered | `interaction-controls.test.tsx`, `search-constraints.test.tsx`, `use-search.test.ts` |
| Mobile sheets | Open/close Filters and Detail sheets + mobile search callback wiring | Covered | `workspace-client.mobile.test.tsx`, browser smoke coverage |
| Keyboard paths | Escape close detail, tab order, Enter/Space on key controls | Partial | Escape covered in `workspace-client.test.tsx` and `smoke.spec.ts`; tab-order/Enter matrix pending |

### Remaining Gaps

- Full keyboard accessibility matrix for all interactive controls (Tab + Enter/Space + focus rings).
- Expand keyboard coverage for mobile sheet focus management after open/close transitions.

## Testing Policy

- Prefer Vitest for deterministic state and interaction logic.
- Keep Playwright smoke limited to critical user journeys.
- Keep visual snapshots narrow (high-value screens only) to avoid baseline churn.
- Use accessibility assertions at both component and route-shell level.

## Declarative Testing Pyramid

| Layer | Goal | What belongs here | File patterns |
|---|---|---|---|
| Unit | Validate pure state logic quickly | Reducers, adapters, token maps, normalization | `src/__tests__/*.test.ts` |
| Component | Validate one component contract | Props -> UI output, callback dispatch, control state | `src/__tests__/*.test.tsx` |
| Integration (frontend) | Validate multi-component flows with providers | URL state + provider interactions, keyboard and control workflows | `src/__tests__/*.test.tsx` (provider-backed) |
| Browser smoke | Validate critical user journeys in real runtime | Search, select, close, panel layout, mobile open/close | `e2e/*smoke*.spec.ts`, `e2e/mobile-workspace.spec.ts` |
| Visual | Catch layout/theme regressions | Desktop and narrow viewport snapshots | `e2e/visual.spec.ts` |

## Test Organization (Declarative)

- `workspace.test.tsx`, `search-constraints.test.tsx`: reducer/state contracts (unit-first).
- `result-*.test.tsx`, `detail-panel.test.tsx`, `filter-panel.interactions.test.tsx`: component contracts.
- `workspace-client.test.tsx`, `interaction-controls.test.tsx`, `keyboard-interactions.test.tsx`: provider-backed integration flows.
- `workspace-client.a11y.test.tsx`: route-shell accessibility contract.
- `e2e/smoke.spec.ts`, `e2e/workspace-panels.spec.ts`, `e2e/mobile-workspace.spec.ts`: critical browser journeys.
- `e2e/visual.spec.ts`: visual baselines for layout/design tokens.

### Declarative Naming Convention

- `*.unit.test.ts(x)`: pure logic, no browser/runtime concerns.
- `*.component.test.tsx`: one component, mocked dependencies allowed.
- `*.integration.test.tsx`: multiple providers/components interacting.
- `e2e/*.spec.ts`: browser-level journeys only.
