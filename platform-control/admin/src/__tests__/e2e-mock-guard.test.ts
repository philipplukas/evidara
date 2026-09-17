/**
 * Every admin Playwright spec must go through `e2e/support/test.ts` (#942).
 *
 * That module installs a fallback `page.route` over `/api/platform-control/**`
 * which aborts and reports any request the spec did not mock. Without it an
 * unmocked request falls through to the Next dev server, which proxies to a
 * platform-control that is not running under test; the screen renders its error
 * state and the spec fails on a missing element far from the real cause. Five
 * distinct specs failed that way across 2026-09-07/08 and 2026-09-17, each once,
 * each green on retry.
 *
 * A spec importing `test` straight from `@playwright/test` silently opts out, so
 * the guard is only as good as this check. It lives in the vitest suite because
 * `npm run check` runs that in CI, while the Playwright suite is a separate job
 * that this file's failure should not depend on.
 */

import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const E2E_DIR = path.resolve(__dirname, "../../e2e");

function specFiles(): string[] {
  return readdirSync(E2E_DIR)
    .filter((name) => name.endsWith(".spec.ts"))
    .sort();
}

describe("admin e2e specs cannot bypass the unmocked-request guard", () => {
  it("finds the specs at all", () => {
    // Without this the assertions below pass over an empty list, which is the
    // failure mode this repo keeps paying for: a check that cannot go red.
    expect(specFiles().length).toBeGreaterThanOrEqual(11);
  });

  it("no spec imports `test` directly from @playwright/test", () => {
    const offenders: string[] = [];
    for (const name of specFiles()) {
      const source = readFileSync(path.join(E2E_DIR, name), "utf8");
      for (const match of source.matchAll(/import\s*\{([^}]*)\}\s*from\s*"@playwright\/test"/g)) {
        // Type-only imports are fine — they carry no runtime `test`, so they
        // cannot skip the fixture. Only a value import of `test` does.
        const names = match[1]
          .split(",")
          .map((entry) => entry.trim())
          .filter(Boolean);
        const bare = names.filter((entry) => !entry.startsWith("type "));
        if (bare.includes("test")) {
          offenders.push(name);
        }
      }
    }
    expect(
      offenders,
      `These specs import \`test\` from @playwright/test and so skip the guard in
e2e/support/test.ts. Import { test, expect } from "./support/test" instead:
${offenders.map((name) => `  e2e/${name}`).join("\n")}`,
    ).toEqual([]);
  });

  it("every spec imports from ./support/test", () => {
    const missing = specFiles().filter(
      (name) => !readFileSync(path.join(E2E_DIR, name), "utf8").includes('from "./support/test"'),
    );
    expect(missing, `specs not using the guarded test module: ${missing.join(", ")}`).toEqual([]);
  });

  it("the guard module still installs a fallback route and asserts on it", () => {
    const guard = readFileSync(path.join(E2E_DIR, "support", "test.ts"), "utf8");
    // Pinning the three things that make it work, so a refactor that removes any
    // one of them fails here rather than silently restoring the flakiness.
    expect(guard).toContain("**/api/platform-control/**");
    expect(guard).toContain("auto: true");
    expect(guard).toContain("route.abort");
    // A spec building its own context must be covered too, or the guard reports
    // "nothing escaped" for a page it never watched.
    expect(guard).toContain("browser.newContext");
  });
});
