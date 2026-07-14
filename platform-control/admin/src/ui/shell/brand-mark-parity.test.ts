import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Cross-surface brand-mark parity guard (admin half).
 *
 * The Evidara mark is the `BrandMark` lattice from `@evidara/shell` — ONE
 * component shared with workspace, not a lookalike. It draws in `currentColor`,
 * so on this dark navy bar it must inherit near-white; a hardcoded navy mark
 * would be invisible here. Only the accent node is tokenised, because it has to
 * stay violet on BOTH grounds.
 *
 * The workspace half lives at
 * `legal-search/frontend/src/__tests__/brand-mark-parity.test.ts`. Either side
 * drifting fails its own surface's `npm run check`.
 */
const sharedTokensCss = readFileSync(join(process.cwd(), "../../styles/tokens/tokens.css"), "utf8");
const adminGlobalsCss = readFileSync(join(process.cwd(), "src/app/globals.css"), "utf8");
const appBarSource = readFileSync(join(process.cwd(), "src/ui/shell/AppBar.tsx"), "utf8");
const adminShellSource = readFileSync(join(process.cwd(), "src/app/AdminShell.tsx"), "utf8");

describe("brand-mark cross-surface contract", () => {
  it("declares the shared accent-node token in tokens.css", () => {
    expect(sharedTokensCss).toContain("--brand-mark-accent:");
  });

  it("has retired the placeholder tile's gradient + serif tokens", () => {
    expect(sharedTokensCss).not.toContain("--brand-mark-gradient:");
    expect(sharedTokensCss).not.toContain("--font-brand-mark:");
  });
});

describe("admin lifts the accent node for its dark ground", () => {
  it("re-points --brand-mark-accent so the hit still carries on navy", () => {
    // The workspace violet is too dark to read on the navy bar, so admin mixes it
    // toward the on-brand foreground. Without this the hit node disappears.
    expect(adminGlobalsCss).toContain(
      "--brand-mark-accent: color-mix(in oklab, var(--accent-core) 52%, var(--admin-on-brand));",
    );
  });
});

describe("admin consumes the shared mark", () => {
  it("renders BrandMark in the AppBar, not a local tile", () => {
    expect(appBarSource).toContain('import { BrandMark } from "@evidara/shell";');
    expect(appBarSource).toContain("<BrandMark size={42} />");
  });

  it("renders BrandMark in the pre-boot shell too", () => {
    expect(adminShellSource).toContain('import { BrandMark } from "@evidara/shell";');
    expect(adminShellSource).toContain("<BrandMark size={42} />");
  });

  it("sets the colour the lattice inherits on this dark bar", () => {
    expect(appBarSource).toContain('color: "var(--admin-on-brand)"');
    expect(adminGlobalsCss).toMatch(
      /\.evidara-shell__mark\s*{[^}]*color:\s*var\(--admin-on-brand\)/,
    );
  });

  it("does not re-inline the retired gradient literal", () => {
    expect(appBarSource).not.toContain("var(--brand-mark-gradient)");
    expect(adminGlobalsCss).not.toContain(
      "linear-gradient(135deg, var(--brand), var(--brand-hover))",
    );
  });

  it("no longer renders the placeholder letter", () => {
    expect(appBarSource).not.toContain(">E<");
    expect(adminShellSource).not.toContain(">E<");
  });
});
