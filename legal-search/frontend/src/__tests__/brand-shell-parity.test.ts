import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Brand-shell parity guard.
 *
 * After PR 6/7 of the brand-parity track, the gradient brand mark and the
 * "Evidara" wordmark live in `@evidara/brand-shell` (`packages/brand-shell`).
 * Workspace consumes them via `<BrandLockup>` and `<BrandHeader>`. This guard
 * catches any future drift that re-implements the brand chrome inline.
 *
 * The same test exists on the admin side at
 * `platform-control/admin/src/__tests__/brand-shell-parity.test.ts` so a
 * regression on either surface fails its own quality gate before merge.
 */

const SRC_ROOT = join(process.cwd(), "src");
const APP_HEADER = join(SRC_ROOT, "components/layout/AppHeader.tsx");

const FORBIDDEN_BRAND_LOCKUP_LITERALS = [
  // The pre-shared-package gradient declaration. Any new occurrence
  // means a contributor re-implemented the brand mark inline.
  "linear-gradient(135deg, var(--brand), var(--brand-hover))",
  // The pre-shared-package single-letter brand mark with a Tailwind
  // text-white class. Catch attempts to draft a new "E" tile in JSX.
  '"text-white font-bold text-sm">E<',
] as const;

function readWorkspaceSource(): { source: string; files: string[] } {
  const files: string[] = [];
  const visit = (dir: string): void => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === "generated" || entry.name === "node_modules") {
          continue;
        }
        visit(path);
      } else if (entry.isFile() && (entry.name.endsWith(".tsx") || entry.name.endsWith(".ts"))) {
        if (entry.name.endsWith(".test.ts") || entry.name.endsWith(".test.tsx")) {
          continue;
        }
        files.push(relative(process.cwd(), path));
      }
    }
  };
  visit(SRC_ROOT);
  files.sort();
  const source = files.map((f) => readFileSync(join(process.cwd(), f), "utf8")).join("\n");
  return { source, files };
}

describe("workspace brand-shell parity", () => {
  it("imports BrandLockup + BrandHeader from the shared package in AppHeader", () => {
    const appHeaderSource = readFileSync(APP_HEADER, "utf8");
    expect(appHeaderSource).toContain('from "@evidara/brand-shell"');
    expect(appHeaderSource).toContain("BrandHeader");
    expect(appHeaderSource).toContain("BrandLockup");
  });

  it("does not re-implement the brand mark or wordmark anywhere outside the shared package", () => {
    const { source } = readWorkspaceSource();
    for (const literal of FORBIDDEN_BRAND_LOCKUP_LITERALS) {
      expect(source).not.toContain(literal);
    }
  });

  it("drops the dead .app-header__brand-mark / __brand-name CSS rules", () => {
    const globalsCss = readFileSync(join(SRC_ROOT, "app/globals.css"), "utf8");
    expect(globalsCss).not.toContain(".app-header__brand-mark");
    expect(globalsCss).not.toContain(".app-header__brand-name");
  });
});
