---
name: run-admin-panel
description: Launch and drive the platform-control admin panel (Next.js react-admin ops UI) end-to-end against the real backend — to see a change working, screenshot a view, or verify list/table behaviour. Use when asked to run/start/screenshot the admin panel, or to confirm an admin change works in the real app (Jurisdictions/Authorities/Sources/Runs lists, pagination, table overflow). Covers Node 22 setup, backend bring-up, the auth env vars, hash routing, and — the hard-won part — why you must drive it with Playwright (prod build), not the Chrome-extension automation against `npm run dev`.
---

# Run the platform-control admin panel

The admin (`platform-control/admin`) is a Next.js 16 + react-admin ops UI. The browser
never talks to Postgres — it calls the platform-control FastAPI API through a BFF proxy
(`src/middleware.ts` rewrites `/api/platform-control/*` → `PLATFORM_CONTROL_API_URL`,
default `http://127.0.0.1:8000`).

## 0. Prereqs (do these first, every time)

- **Node 22 via nvm.** System node breaks the build/tests. From `platform-control/admin`:
  `source ~/.config/nvm/nvm.sh; nvm use` (reads `.nvmrc` → 22). Source with `;` not `&&`.
- **Deps:** `npm ci` inside `platform-control/admin` if `node_modules` is missing (each JS
  surface owns its own — never `npm install` at `legal-search/` or repo root).

## 1. Backend on :8000 (real data)

Check whether it's already up — it usually is, with the full seed (2,169 jurisdictions,
42 authorities, real runs incl. the ADR-0033 "dog axis repro"):

```bash
curl -s http://127.0.0.1:8000/v1/reference-data/jurisdictions | \
  python3 -c "import sys,json;print(len(json.load(sys.stdin)['data']),'jurisdictions')"
curl -s http://127.0.0.1:8000/stats | head -c 120
```

If it is NOT up, start it (canonical helper — needs Postgres; the demo script bootstraps it):

```bash
bash scripts/platform-control-demo.sh bootstrap   # DB + migrations + seed
bash scripts/platform-control-demo.sh api         # uvicorn platform_control.main:app on :8000
```

Docker alternative: `docker compose -f docker-compose.local.yml --profile apps up platform-control-api`.

## 2. Auth env vars (or the app shows NO data)

react-admin gates on a role. Without these the lists render empty / redirect:

- `NEXT_PUBLIC_USER_ROLE=admin` and `NEXT_PUBLIC_ADMIN_ALLOWED_ROLES=admin` — **build-time**
  (inlined; must be set for `npm run build`, not just `npm start`).
- `PLATFORM_CONTROL_API_URL=http://127.0.0.1:8000` — **runtime** (read by middleware).

## 3a. For a human to click around → dev server

```bash
bash scripts/platform-control-demo.sh admin   # = npm run dev, http://localhost:3000
```
(Set the two `NEXT_PUBLIC_*` vars in `platform-control/admin/.env.local` first.)

## 3b. For automated driving / screenshots → PRODUCTION build, then Playwright

**Do NOT try to drive `npm run dev` with the Chrome-extension automation.** This Next 16 /
React 19 dev server never reports `document_idle` (HMR keeps it busy), so
`claude-in-chrome` screenshot/read_page calls time out ("Script injection timed out",
"waited 45000ms for document_idle"). A production build removes HMR:

```bash
cd platform-control/admin
source ~/.config/nvm/nvm.sh; nvm use
NEXT_PUBLIC_USER_ROLE=admin NEXT_PUBLIC_ADMIN_ALLOWED_ROLES=admin npm run build
PLATFORM_CONTROL_API_URL=http://127.0.0.1:8000 PORT=3000 npm start &   # http://localhost:3000
```

Then drive with **Playwright** (already a dep here, chromium cached), which is fully under
your control and yields real screenshots + DOM assertions. Run the bundled driver:

```bash
node .claude/skills/run-admin-panel/drive.mjs   # edit the absolute import path inside if the repo moved
```

It visits each view, waits for the table, and prints the count caption, pager text, and the
table's scroll geometry, then screenshots each to the scratchpad. Key trick: when the driver
lives outside the package, import Playwright by **absolute path** to the admin's node_modules
(CommonJS default import), because ESM won't resolve a bare `playwright` from elsewhere.

## Routing (hash-based)

`/#/jurisdictions` · `/#/authorities` · `/#/sources` · `/#/runs-v2` · `/#/corrections`
· `/#/preview-review-v2` · dashboard at `/`.

## What "working" looks like (verified 2026-07-18)

- Jurisdictions: caption "2169 JURISDICTIONS", pager "Page 1 of 44 · 2169 total", 50 rows/page,
  Next advances 1→2. Authorities: "42 AUTHORITIES".
- Run queue table: `<table class="min-w-full">` inside `<div class="overflow-x-auto">`,
  `scrollWidth (1267) > clientWidth (1014)` → scrolls horizontally instead of clipping the
  right columns (CREATED/UPDATED/ACTIONS). Narrow tables (≤6 cols) do not force scroll.

## Gotchas recap

- System node → dishonest gates and build breakage; always `nvm use`.
- Missing `NEXT_PUBLIC_*` role vars → empty lists.
- Chrome-extension automation vs `npm run dev` → injection timeouts; use prod build + Playwright.
- Reference-data lists (jurisdictions/authorities/sources) return the FULL array; the admin
  paginates client-side (`applyClientListWindow`), so the total count is the array length.
