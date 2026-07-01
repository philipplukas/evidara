import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Cross-surface brand-mark parity guard.
 *
 * The "Evidara" brand-mark tile (gradient navy square + serif "E") is
 * rendered inline in two places: workspace's `AppHeader` and admin's
 * `AppBar`. The fill and the display-letter typeface are a *shared* brand
 * contract — they must consume `--brand-mark-gradient` and
 * `--font-brand-mark` from `styles/tokens/tokens.css`.
 *
 * This test enforces the workspace half. The admin half is enforced by the
 * mirror at `platform-control/admin/src/ui/shell/brand-mark-parity.test.ts`.
 * Either side drifting fails its own surface's `npm run check`.
 */
const sharedTokensCss = readFileSync(join(process.cwd(), "../../styles/tokens/tokens.css"), "utf8");
const workspaceGlobalsCss = readFileSync(join(process.cwd(), "src/app/globals.css"), "utf8");

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

describe("workspace brand-mark consumes shared tokens", () => {
  it("maps --font-brand-mark onto the workspace's loaded serif face", () => {
    expect(workspaceGlobalsCss).toMatch(/--font-brand-mark:\s*var\(--font-serif\)/);
  });

  it("renders .app-header__brand-mark with the shared gradient + serif", () => {
    expect(workspaceGlobalsCss).toContain("background: var(--brand-mark-gradient);");
    expect(workspaceGlobalsCss).toContain("font-family: var(--font-brand-mark);");
  });

  it("does not re-inline the brand-mark gradient literal", () => {
    expect(workspaceGlobalsCss).not.toContain(
      "linear-gradient(135deg, var(--brand), var(--brand-hover))",
    );
  });
});
