/**
 * Run-identity endpoint — lets a Playwright run prove it is talking to the
 * server it started, rather than to a stale container or another lane's dev
 * server that happens to hold the port. See
 * `scripts/e2e/playwright-server-identity.mjs` for the full rationale.
 *
 * Inert outside tests: without `E2E_RUN_ID` in the environment this 404s, so a
 * production deployment exposes nothing.
 */

/** Must match the `surface` the Playwright config declares for this app. */
const SURFACE = "platform-control-admin";

const STARTED_AT = new Date().toISOString();

export const dynamic = "force-dynamic";

export function GET(): Response {
  const runId = process.env.E2E_RUN_ID?.trim();
  if (!runId) {
    return new Response("Not Found", { status: 404 });
  }

  return Response.json(
    { surface: SURFACE, runId, pid: process.pid, startedAt: STARTED_AT },
    { headers: { "cache-control": "no-store" } },
  );
}
