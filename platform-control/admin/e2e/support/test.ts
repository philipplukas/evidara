/**
 * The admin Playwright `test`, with a guard against requests escaping the mocks.
 *
 * Every spec in this suite mocks platform-control with `page.route`, so nothing
 * should reach a real backend. When a request matches no spec route it falls
 * through to the Next dev server, whose middleware proxies `/api/platform-control/*`
 * to `PLATFORM_CONTROL_API_URL` — not running under test. The fetch fails, the
 * screen renders its error state, and the assertion that follows reports
 * `element(s) not found`.
 *
 * That is #942. It reads as flakiness because *which* request escapes depends on
 * render order and timing, so a different spec fails each run and a retry usually
 * passes: 2026-09-07/08 gave `reference-data:162`, `source-create:342` and
 * `blueprint-inventory:161`; 2026-09-17 added `preview-review-v2:133` and
 * `operator-usability:258`, on two runs of one unrelated four-line YAML change.
 * Five distinct specs, none near the change in flight.
 *
 * The fix is not `retries`. A retry turns the build green without anyone learning
 * which request was unmocked, and this is the only layer that sees layout,
 * stylesheets and routing — its failures must stay worth reading.
 */

import type { BrowserContext, Page } from "@playwright/test";
import { test as base, expect } from "@playwright/test";

/**
 * `src/middleware.ts` matches `/api/platform-control/:path*` and proxies it. That
 * prefix is the whole surface a spec can fail to mock; everything else the page
 * requests is served by Next itself and is not this guard's business.
 */
const PROXIED_API = "**/api/platform-control/**";

// Playwright types an auto fixture that yields nothing as `void`; that is the
// documented shape for `{ auto: true }`, and the rule targets `void` in ordinary
// positions rather than this one.
// biome-ignore lint/suspicious/noConfusingVoidType: see above
export const test = base.extend<{ mockedApiOnly: void }>({
  mockedApiOnly: [
    async ({ page, browser }, use, testInfo) => {
      const escaped: string[] = [];

      // Registered before any spec's own routes, which is what makes it a
      // fallback rather than an override: Playwright checks page handlers in
      // reverse registration order, so the most recently added wins and this one
      // is consulted only when nothing else matched. A context-level handler is
      // likewise consulted only after every page-level one.
      const install = async (target: Page | BrowserContext) => {
        await target.route(PROXIED_API, async (route) => {
          const request = route.request();
          escaped.push(`${request.method()} ${new URL(request.url()).pathname}`);
          // Abort rather than continue. Continuing reaches the dev server, which
          // reports ECONNREFUSED from somewhere far from the spec and leaves the
          // test failing on a missing element instead of on the missing mock.
          await route.abort("failed");
        });
      };

      await install(page);

      // A spec that builds its own context — operator-usability's dark-OS test
      // needs `colorScheme: "dark"`, which the fixture page cannot give it —
      // would otherwise run unguarded, and the guard would report "nothing
      // escaped" for a page it never watched. Patch `newContext` for the
      // duration of the test so those contexts are covered too. Tests run
      // sequentially within a worker, so the patch cannot leak across them, and
      // it is restored below regardless.
      const originalNewContext = browser.newContext.bind(browser);
      browser.newContext = async (...args) => {
        const context = await originalNewContext(...args);
        await install(context);
        return context;
      };

      try {
        await use();
      } finally {
        browser.newContext = originalNewContext;
      }

      if (escaped.length > 0) {
        const unique = [...new Set(escaped)];
        // An annotation as well as the failure, so the escaped path is visible
        // in the HTML report without opening the trace.
        testInfo.annotations.push({
          type: "unmocked-request",
          description: unique.join(", "),
        });
      }

      expect(
        escaped,
        [
          "This spec issued a platform-control request it does not mock:",
          ...[...new Set(escaped)].map((entry) => `  ${entry}`),
          "",
          "It was aborted rather than proxied, so any 'element(s) not found'",
          "failure above is a consequence of this, not a separate problem.",
          "Add a page.route for the path, or widen an existing one.",
        ].join("\n"),
      ).toEqual([]);
    },
    { auto: true },
  ],
});

export type { Page, Route } from "@playwright/test";
export { expect };
