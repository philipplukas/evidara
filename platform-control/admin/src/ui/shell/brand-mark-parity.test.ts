import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Cross-surface brand-mark parity guard (admin half).
 *
 * The "Evidara" brand-mark tile (gradient navy square + serif "E") is
 * rendered inline in `AppBar.tsx` and in workspace's `AppHeader`. The
 * fill and the display-letter typeface are a *shared* brand contract —
 * they must consume `--brand-mark-gradient` and `--font-brand-mark` from
 * `styles/tokens/tokens.css`.
 *
 * The workspace half lives at
 * `legal-search/frontend/src/__tests__/brand-mark-parity.test.ts`. Either
 * side drifting fails its own surface's `npm run check`.
 */
const sharedTokensCss = readFileSync(join(process.cwd(), "../../styles/tokens/tokens.css"), "utf8");
const adminGlobalsCss = readFileSync(join(process.cwd(), "src/app/globals.css"), "utf8");
const appBarSource = readFileSync(join(process.cwd(), "src/ui/shell/AppBar.tsx"), "utf8");

describe("brand-mark cross-surface contract", () => {
  it("declares the shared brand-mark gradient + serif tokens in tokens.css", () => {
    expect(sharedTokensCss).toContain("--brand-mark-gradient:");
    expect(sharedTokensCss).toContain("--font-brand-mark:");
  });

  it("ties --brand-mark-gradient to the shared --brand / --brand-hover pair", () => {
    expect(sharedTokensCss).toContain(
      "--brand-mark-gradient: linear-gradient(135deg, var(--brand), var(--brand-hover));",
    );
  });
});

describe("admin brand-mark consumes shared tokens", () => {
  it("maps --font-brand-mark onto admin's loaded serif face", () => {
    expect(adminGlobalsCss).toMatch(/--font-brand-mark:\s*var\(--font-admin-serif\)/);
  });

  it("renders the AppBar brand-mark tile with the shared gradient + serif", () => {
    expect(appBarSource).toContain('background: "var(--brand-mark-gradient)"');
    expect(appBarSource).toContain('fontFamily: "var(--font-brand-mark)"');
  });

  it("does not re-inline the brand-mark gradient literal", () => {
    // `var(--font-admin-serif)` is still used elsewhere in AppBar (the
    // route-aware page-title portal) and is intentionally surface-local —
    // we only forbid the gradient literal, since that's the shared half
    // of the brand-mark contract.
    expect(appBarSource).not.toContain(
      'background: "linear-gradient(135deg, var(--brand), var(--brand-hover))"',
    );
  });
});
