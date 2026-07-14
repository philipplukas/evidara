import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Cross-surface brand-mark parity guard.
 *
 * The Evidara mark is the `BrandMark` lattice from `@evidara/shell` — ONE
 * component consumed by both surfaces, not two lookalikes. Its strokes and nodes
 * are drawn in `currentColor` so it inherits navy on workspace's light header and
 * near-white on admin's dark navy bar. That inheritance is the whole design: a
 * hardcoded navy mark would be invisible on the admin bar.
 *
 * This test enforces the workspace half. The admin half is enforced by the mirror
 * at `platform-control/admin/src/ui/shell/brand-mark-parity.test.ts`. Either side
 * drifting fails its own surface's `npm run check`.
 */
const sharedTokensCss = readFileSync(join(process.cwd(), "../../styles/tokens/tokens.css"), "utf8");
const workspaceGlobalsCss = readFileSync(join(process.cwd(), "src/app/globals.css"), "utf8");
const appHeader = readFileSync(join(process.cwd(), "src/components/layout/AppHeader.tsx"), "utf8");
const brandMark = readFileSync(join(process.cwd(), "../../styles/shell/BrandMark.tsx"), "utf8");

describe("brand-mark cross-surface contract", () => {
  it("declares the shared accent-node token in tokens.css", () => {
    expect(sharedTokensCss).toContain("--brand-mark-accent:");
  });

  it("ties the accent node to the single action colour", () => {
    expect(sharedTokensCss).toContain("--brand-mark-accent: var(--accent-core);");
  });

  it("has retired the placeholder tile's gradient + serif tokens", () => {
    // The navy-gradient-tile-with-an-E is gone. If either token comes back, so has
    // the placeholder.
    expect(sharedTokensCss).not.toContain("--brand-mark-gradient:");
    expect(sharedTokensCss).not.toContain("--font-brand-mark:");
  });
});

describe("the mark itself", () => {
  it("draws the lattice in currentColor so it can invert per surface", () => {
    expect(brandMark).toContain('stroke="currentColor"');
    expect(brandMark).toContain('fill="currentColor"');
  });

  it("colours ONLY the accent node from a token", () => {
    expect(brandMark).toContain('fill="var(--brand-mark-accent)"');
    // A second hardcoded colour would break the single-accent rule.
    expect(brandMark).not.toMatch(/fill="#[0-9a-fA-F]{3,8}"/);
    expect(brandMark).not.toMatch(/stroke="#[0-9a-fA-F]{3,8}"/);
  });

  it("keeps the hit node off-centre — the asymmetry is the idea", () => {
    // Centre of the 32x32 grid is [16, 16]. The hit must not sit there.
    expect(brandMark).toContain("const HIT: readonly [number, number] = [23, 9];");
  });

  it("ships a compact variant, because the full lattice dies at favicon size", () => {
    expect(brandMark).toContain("export function BrandMarkCompact");
  });
});

describe("workspace consumes the shared mark", () => {
  it("renders BrandMark from @evidara/shell, not a local lookalike", () => {
    expect(appHeader).toContain('import { BrandMark } from "@evidara/shell";');
    expect(appHeader).toContain("<BrandMark size={32} />");
  });

  it("sets the colour the lattice inherits on this light header", () => {
    expect(workspaceGlobalsCss).toMatch(/\.app-header__brand-mark\s*{[^}]*color:\s*var\(--brand\)/);
  });

  it("does not re-inline the retired gradient literal", () => {
    expect(workspaceGlobalsCss).not.toContain(
      "linear-gradient(135deg, var(--brand), var(--brand-hover))",
    );
  });
});
