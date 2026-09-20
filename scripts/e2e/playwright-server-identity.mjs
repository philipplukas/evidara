/**
 * Run identity for Playwright suites — proves a run is talking to the server
 * IT started, not to whatever happens to answer on the port.
 *
 * Why this exists (all four observed in a single day):
 *
 *  1. A lane's e2e run attached to ANOTHER lane's `next dev` on port 3000
 *     (`reuseExistingServer: true`) and reported 19 green against a tree that
 *     did not contain its changes.
 *  2. A lane's run bound to a STALE DOCKER CONTAINER on port 3101 after its own
 *     dev server exited, and reproduced the exact bug it had just fixed. It was
 *     only caught by hand-probing the DOM for obsolete class names.
 *  3. Root-owned `test-results/` left behind by the containerised VRT script.
 *  4. A repo-root `node_modules` symlink let resolution escape the worktree.
 *
 * Why a per-run nonce over the obvious alternatives:
 *
 *  - Unique PORTS are a proxy, not an answer. They do not catch a stale
 *    container already listening on the port you picked (case 2), a forgotten
 *    background server, or a second lane that picked the same port. Identity
 *    catches all three; ports catch none of them reliably.
 *  - A BUILD ID distinguishes trees but not processes. Two servers built from
 *    the same commit are indistinguishable, so case 2 (stale container, same
 *    branch, older build) can still slip through, and Next's dev build id is
 *    not stable or exposed anyway.
 *  - A DOM MARKER needs a browser and a rendered page, so it can only fail
 *    mid-suite, per-test, after the misattribution has already happened. The
 *    whole point is to fail BEFORE the first test.
 *
 * So: the Playwright config mints a random `E2E_RUN_ID`, injects it into every
 * `webServer` it starts, and this global setup asserts — over HTTP, before any
 * browser launches — that each target echoes that exact nonce back. A server
 * this run did not start cannot know the nonce.
 *
 * The endpoint is inert outside tests: it 404s unless `E2E_RUN_ID` is set, so
 * it exposes nothing in a production deployment.
 */

/** Path each Next surface serves its identity on. */
export const IDENTITY_PATH = "/api/e2e-identity";

/**
 * Reuse is OPT-IN. The default is a fresh server per run, because
 * `reuseExistingServer: true` is precisely how cases 1 and 2 happened.
 */
export function reuseExistingServer() {
  const raw = process.env.PLAYWRIGHT_REUSE_SERVER?.trim().toLowerCase();
  return raw === "1" || raw === "true";
}

/**
 * The nonce for this run. Stable within the process; inherited by every
 * `webServer` child Playwright spawns.
 */
export function ensureRunId() {
  if (!process.env.E2E_RUN_ID?.trim()) {
    process.env.E2E_RUN_ID = `run-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  }
  return process.env.E2E_RUN_ID;
}

/**
 * Declare which servers this run is responsible for. Each entry is
 * `{ url, surface }`; `surface` must match the constant baked into that app's
 * identity route, so a run pointed at the WRONG APP fails differently (and
 * more usefully) than a run pointed at a stale copy of the right one.
 */
export function declareIdentityTargets(targets) {
  process.env.E2E_IDENTITY_TARGETS = JSON.stringify(targets);
  return targets;
}

function readTargets() {
  const raw = process.env.E2E_IDENTITY_TARGETS?.trim();
  if (!raw) {
    return [];
  }
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    throw new Error(`E2E_IDENTITY_TARGETS is not valid JSON: ${raw}`);
  }
}

function banner(lines) {
  const bar = "=".repeat(72);
  return ["", bar, "E2E RUN IDENTITY CHECK FAILED", bar, ...lines, bar, ""].join("\n");
}

async function fetchIdentity(url, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      signal: controller.signal,
      headers: { accept: "application/json" },
      cache: "no-store",
    });
    const text = await response.text();
    return { status: response.status, text };
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Assert one target is the server this run started.
 *
 * @param {{url: string, surface: string}} target
 * @param {{expectedRunId: string, enforceRunId: boolean, timeoutMs?: number}} options
 */
export async function assertServerIdentity(target, options) {
  const { expectedRunId, enforceRunId, timeoutMs = 15_000 } = options;
  const identityUrl = new URL(IDENTITY_PATH, target.url).toString();

  let result;
  try {
    result = await fetchIdentity(identityUrl, timeoutMs);
  } catch (error) {
    throw new Error(
      banner([
        `Could not reach the identity endpoint:  ${identityUrl}`,
        `  cause: ${error instanceof Error ? error.message : String(error)}`,
        "",
        "Likely cause: the server this run started is not listening on that",
        "URL — it crashed at boot, or the port is held by something else.",
      ]),
    );
  }

  if (result.status !== 200) {
    throw new Error(
      banner([
        `${identityUrl} answered HTTP ${result.status}, not 200.`,
        "",
        "SOMETHING IS LISTENING ON THIS PORT, BUT IT IS NOT THIS TEST RUN'S SERVER.",
        "",
        "Likely causes, most common first:",
        `  1. A STALE DOCKER CONTAINER is bound to ${target.url}. Check:`,
        "       docker ps --filter publish=" + (new URL(target.url).port || "80"),
        "  2. A dev server from ANOTHER WORKTREE/LANE is on this port. Check:",
        "       lsof -i :" + (new URL(target.url).port || "80"),
        "  3. An older build of this app that predates the identity route.",
        "",
        "Whatever answered would have served your tests silently, and any",
        "green result would have described that server, not your changes.",
        `  response body (truncated): ${result.text.slice(0, 200)}`,
      ]),
    );
  }

  let payload;
  try {
    payload = JSON.parse(result.text);
  } catch {
    throw new Error(
      banner([
        `${identityUrl} returned 200 but not JSON. Something else owns this port.`,
        `  response body (truncated): ${result.text.slice(0, 200)}`,
      ]),
    );
  }

  if (payload.surface !== target.surface) {
    throw new Error(
      banner([
        `${target.url} is serving the WRONG APPLICATION.`,
        `  expected surface: ${target.surface}`,
        `  actual surface:   ${payload.surface}`,
        "",
        "Likely cause: two surfaces were configured on the same port, or a",
        "dev server for a different app in this monorepo is already running.",
      ]),
    );
  }

  if (!enforceRunId) {
    console.warn(
      `[e2e-identity] ${target.surface} @ ${target.url}: surface verified, run id ` +
        "NOT enforced (PLAYWRIGHT_EXTERNAL_BASE_URL points at a server this run " +
        "cannot stamp). A stale deploy behind that URL would go undetected.",
    );
    return payload;
  }

  if (payload.runId !== expectedRunId) {
    throw new Error(
      banner([
        `${target.url} is a DIFFERENT SERVER than this run started.`,
        `  this run's id: ${expectedRunId}`,
        `  server's id:   ${payload.runId ?? "(none)"}`,
        `  server pid:    ${payload.pid ?? "(unknown)"}`,
        `  server booted: ${payload.startedAt ?? "(unknown)"}`,
        "",
        "The server answered, and it is the right app — but it is NOT the",
        "process this run launched. Likely causes, most common first:",
        `  1. A STALE DOCKER CONTAINER on ${target.url} outlived a previous run:`,
        "       docker ps --filter publish=" + (new URL(target.url).port || "80"),
        "  2. Another lane/worktree is serving this port from a different tree:",
        "       lsof -i :" + (new URL(target.url).port || "80"),
        "  3. A previous run's dev server leaked and was never reaped.",
        "",
        "Had this check not run, the suite would have passed or failed against",
        "code you did not write.",
        "",
        "Kill the other server and re-run. If you MEANT to attach to a server",
        "you started yourself, start it with the same nonce and opt in:",
        "    E2E_RUN_ID=my-lane npm run dev",
        "    E2E_RUN_ID=my-lane PLAYWRIGHT_REUSE_SERVER=1 npx playwright test",
        "Reuse alone is not enough — the nonce is what proves it is your server.",
      ]),
    );
  }

  return payload;
}

/**
 * Fetch the app shell once so the first test does not pay for it.
 *
 * The identity check above proves the server is ours, but it only touches
 * `/api/e2e-identity` — a route that compiles and caches separately from the
 * page. The first test to open the app was still paying first-byte costs
 * inside its own 5s assertion budget. One bounded GET here moves that cost out
 * of the tests, where it reads as "element(s) not found" rather than as
 * latency.
 *
 * Never fatal: a warm-up that fails tells us nothing the identity check has
 * not already established, and failing here would turn a slow server into an
 * unexplained global-setup error.
 */
async function warmAppShell(target, timeoutMs = 60_000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const startedAt = Date.now();
  try {
    const response = await fetch(target.url, {
      signal: controller.signal,
      headers: { accept: "text/html" },
    });
    // Drain it: the body is what the server had to render.
    await response.text();
    console.log(
      `[e2e-identity] warmed ${target.surface} @ ${target.url} in ${Date.now() - startedAt}ms (HTTP ${response.status})`,
    );
  } catch (error) {
    console.log(
      `[e2e-identity] warm-up skipped for ${target.surface}: ${error instanceof Error ? error.message : String(error)}`,
    );
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Playwright `globalSetup`. Runs once, before any browser starts, after
 * `webServer` entries are up.
 */
export default async function globalSetup() {
  const targets = readTargets();
  if (targets.length === 0) {
    return;
  }

  const expectedRunId = ensureRunId();
  // The nonce is enforced even under PLAYWRIGHT_REUSE_SERVER=1 — reuse is only
  // safe if you exported the SAME E2E_RUN_ID to the server you started, and
  // that is exactly the property worth checking. Opting into reuse without
  // sharing the nonce is the failure mode that caused the false green, so it
  // must fire, not be waved through.
  //
  // Only a genuinely external target (a deployed environment behind
  // PLAYWRIGHT_EXTERNAL_BASE_URL, which this run cannot stamp) is exempt, and
  // even then the surface is still verified.
  const enforceRunId = process.env.E2E_IDENTITY_EXTERNAL !== "1";

  for (const target of targets) {
    const payload = await assertServerIdentity(target, { expectedRunId, enforceRunId });
    await warmAppShell(target);
    if (enforceRunId) {
      console.log(
        `[e2e-identity] OK ${target.surface} @ ${target.url} (run ${payload.runId}, pid ${payload.pid})`,
      );
    }
  }
}
