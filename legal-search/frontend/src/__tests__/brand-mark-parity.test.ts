import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Cross-surface brand-mark parity guard (workspace half).
 *
 * The Evidara mark used to be a gradient navy tile with a serif "E", rendered
 * *inline* in three places — workspace's `AppHeader`, admin's `AppBar`, and
 * admin's pre-boot `AdminShell`. Three copies of a drawing, held together by
 * assertions that they each read the same two tokens. That is a weak contract:
 * it can only catch a colour drifting, never the geometry.
 *
 * The mark is now a single shared component, `BrandMark` in
 * `styles/shell/BrandMark.tsx`, so there is exactly one drawing and it cannot
 * drift from itself. What this test guards is that the workspace still consumes
 * it rather than re-inlining a local copy, and that the retired tokens have not
 * crept back.
 *
 * The admin half is enforced by the mirror at
 * `platform-control/admin/src/ui/shell/brand-mark-parity.test.ts`. Either side
 * drifting fails its own surface's `npm run check`.
 */
const sharedTokensCss = readFileSync(join(process.cwd(), "../../styles/tokens/tokens.css"), "utf8");
const workspaceGlobalsCss = readFileSync(join(process.cwd(), "src/app/globals.css"), "utf8");
const appHeaderSource = readFileSync(
  join(process.cwd(), "src/components/layout/AppHeader.tsx"),
  "utf8",
);

describe("brand-mark cross-surface contract", () => {
  it("declares the shared accent-node token in tokens.css", () => {
    expect(sharedTokensCss).toContain("--brand-mark-accent: var(--accent-core);");
  });

  it("has fully retired the gradient-tile tokens", () => {
    // The old contract. If either reappears, someone is rebuilding the tile.
    expect(sharedTokensCss).not.toContain("--brand-mark-gradient:");
    expect(sharedTokensCss).not.toContain("--font-brand-mark:");
  });
});

describe("workspace consumes the shared BrandMark", () => {
  it("imports it from @evidara/shell rather than re-inlining a mark", () => {
    expect(appHeaderSource).toContain('import { BrandMark } from "@evidara/shell"');
    expect(appHeaderSource).toContain("<BrandMark");
  });

  it("feeds the lattice navy via currentColor on the workspace's light header", () => {
    // BrandMark draws in `currentColor` precisely so admin can put it on a dark
    // ground. That only works if each surface actually sets a colour.
    expect(workspaceGlobalsCss).toMatch(/\.app-header__brand-mark \{[^}]*color:\s*var\(--brand\);/);
  });

  it("does not rebuild the retired gradient tile", () => {
    expect(workspaceGlobalsCss).not.toContain("var(--brand-mark-gradient)");
    expect(workspaceGlobalsCss).not.toContain("var(--font-brand-mark)");
    expect(workspaceGlobalsCss).not.toContain(
      "linear-gradient(135deg, var(--brand), var(--brand-hover))",
    );
  });
});
