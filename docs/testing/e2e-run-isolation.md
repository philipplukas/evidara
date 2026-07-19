# E2E Run Isolation

A test result is only worth something if you know which server produced it. This
page describes how Playwright runs in this repo prove that.

## The problem

In a single day, four separate lanes reported results that described the wrong
tree:

1. A lane's e2e run attached to **another lane's dev server on :3000**
   (`reuseExistingServer: true`) and reported 19 green against a tree that did
   not contain its changes.
2. A lane's run bound to a **stale Docker container on :3101** after its own dev
   server exited, and reported the exact bug it had just fixed. Re-run in
   isolation it was 19/19 green.
3. `scripts/playwright-visual-update-docker.sh` ran as root and left root-owned
   `test-results/` and `playwright-report/` in the worktree, breaking the next
   local run with `EACCES`.
4. A repo-root `node_modules` symlink let module resolution escape a worktree
   (guarded separately by `scripts/check-js-workspace-hygiene.sh`).

## Why unique ports are not the answer

Assigning each lane its own port is a proxy for the property you actually want.
A port does not tell you **who is listening on it**. It does not catch:

- a stale container already bound to the port you picked (case 2),
- a leaked dev server from a previous run,
- another lane that happened to pick the same port.

The property that matters is **identity**: a run must verify it is talking to
the server *it started*.

## The mechanism: a per-run nonce

`scripts/e2e/playwright-server-identity.mjs` is a shared Playwright
`globalSetup` used by both surfaces.

1. The Playwright config mints a random `E2E_RUN_ID` for the run.
2. It injects that nonce into every `webServer` it starts.
3. Each Next surface serves it back at `GET /api/e2e-identity`, together with
   the surface name, pid, and boot time.
4. Before any browser launches, `globalSetup` fetches that endpoint on every
   target and asserts the nonce matches.

A server this run did not start cannot know the nonce, so every case above
fails fast with a message naming the likely cause — rather than passing
silently and misattributing the result.

The endpoint 404s unless `E2E_RUN_ID` is set, so it exposes nothing in a
production deployment.

### Why a nonce and not the alternatives

| Candidate | Why not |
|---|---|
| Unique ports | A proxy, not an identity. Misses a stale container on the port you chose. |
| Build id | Distinguishes trees, not processes. Two servers from the same commit are indistinguishable, so case 2 still slips through — and Next's dev build id is neither stable nor exposed. |
| DOM marker | Needs a browser and a rendered page, so it can only fail per-test, mid-suite, after the misattribution has happened. The point is to fail *before* the first test. |

## Reuse is opt-in, and still checked

`reuseExistingServer` defaults to **false** on both surfaces — attaching to a
stray server is how cases 1 and 2 happened.

Reuse remains available, but the nonce is enforced *even then*: opting in
without sharing the nonce is exactly the dangerous case, so it fires rather
than being waved through. To reuse a server you started yourself, give both
sides the same nonce:

```bash
E2E_RUN_ID=my-lane npm run dev -- --webpack --port 3000
E2E_RUN_ID=my-lane PLAYWRIGHT_REUSE_SERVER=1 npx playwright test
```

Only a genuinely external target (`PLAYWRIGHT_EXTERNAL_BASE_URL`, e.g. a
deployed environment this run cannot stamp) is exempt from the nonce; its
*surface* is still verified.

## Choosing ports per lane

Ports are a convenience on top of the identity check, not a substitute for it.

| Variable | Surface | Default |
|---|---|---|
| `ADMIN_E2E_PORT` | `platform-control/admin` | `3000` |
| `FRONTEND_E2E_PORT` | `legal-search/frontend` | `3101` |
| `ADMIN_E2E_PORT` | admin server started by the frontend suite | `3100` |

The frontend config publishes the resolved URLs into
`PLAYWRIGHT_EXTERNAL_BASE_URL`, `PLAYWRIGHT_ADMIN_BASE_URL`, and
`PLAYWRIGHT_EXPECTED_CONTROL_PANEL_URL`, so specs asserting cross-surface
navigation follow the ports the run actually chose instead of re-deriving a
hardcoded default.

## Container artifact ownership

`scripts/playwright-visual-update-docker.sh` runs `docker run --user
$(id -u):$(id -g)`, so the container's `test-results/` and
`playwright-report/` are owned by the invoking user and the next local run does
not die with `EACCES`.

That script's image (`playwright:v1.59.1-jammy`, Ubuntu 22.04, Node 24) matches
CI (`ubuntu-latest`, Node 22) on neither OS nor Node; the header says so
explicitly rather than claiming parity. Aligning the image would rewrite every
committed `-linux.png`, which is baseline territory (#611), so it is
deliberately left alone.

## Verifying the guard still works

`scripts/tests/test_playwright_server_identity.py` asserts **both directions**
against fixture servers: the check passes for a server presenting this run's
nonce, and fails — naming the cause — for a stale nonce, a missing identity
route, a different surface, and a dead port. A guard that cannot be shown to
fire is indistinguishable from no guard, and worse, because it is trusted.
