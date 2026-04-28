import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Brand-shell parity guard.
 *
 * After PR 6/7 of the brand-parity track, the gradient brand mark and the
 * "Evidara" wordmark live in `@evidara/brand-shell` (`packages/brand-shell`).
 * Admin consumes them via `<BrandLockup>` and `<BrandHeader>`. This guard
 * catches any future drift that re-implements the brand chrome inline in
 * an admin shell or resource component.
 *
 * The same test exists on the workspace side at
 * `legal-search/frontend/src/__tests__/brand-shell-parity.test.ts` so a
 * regression on either surface fails its own quality gate before merge.
 */

const SRC_ROOT = join(process.cwd(), "src");
const APP_BAR = join(SRC_ROOT, "ui/shell/AppBar.tsx");

const FORBIDDEN_BRAND_LOCKUP_LITERALS = [
  // The pre-shared-package gradient declaration that previously appeared
  // inline in `AppBar.tsx`. Any new occurrence means a contributor
  // re-implemented the brand mark instead of mounting `<BrandLockup>`.
  "linear-gradient(135deg, var(--brand), var(--brand-hover))",
  // The admin's pre-shared-package wordmark eyebrow — a 10px uppercase
  // tracked "Evidara" rendered above a "Control plane" label. The shared
  // lockup folds these into a single wordmark + sub-label pair.
  "text-[10px] font-semibold tracking-[0.16em] text-[var(--admin-on-brand-muted)] uppercase",
] as const;

function readAdminSource(): { source: string; files: string[] } {
  const files: string[] = [];
  const visit = (dir: string): void => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === "node_modules") {
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

describe("admin brand-shell parity", () => {
  it("imports BrandLockup + BrandHeader from the shared package in AppBar", () => {
    const appBarSource = readFileSync(APP_BAR, "utf8");
    expect(appBarSource).toContain('from "@evidara/brand-shell"');
    expect(appBarSource).toContain("BrandHeader");
    expect(appBarSource).toContain("BrandLockup");
  });

  it("does not re-implement the brand mark or wordmark anywhere in the admin tree", () => {
    const { source } = readAdminSource();
    for (const literal of FORBIDDEN_BRAND_LOCKUP_LITERALS) {
      expect(source).not.toContain(literal);
    }
  });
});
