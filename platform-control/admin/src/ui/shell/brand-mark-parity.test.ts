import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Cross-surface brand-mark parity guard (admin half).
 *
 * See the workspace mirror at
 * `legal-search/frontend/src/__tests__/brand-mark-parity.test.ts` for the full
 * rationale. In short: the mark used to be a gradient tile inlined in three
 * places, and is now the single shared `BrandMark` component in
 * `styles/shell/BrandMark.tsx`.
 *
 * Admin is the harder half, because it renders the mark on *two different
 * grounds*: `AppBar` sits on the dark navy brand header (so the lattice must
 * inherit the near-white `--admin-on-brand`, and the accent node must be lifted
 * or it goes muddy), while the pre-boot `AdminShell` states sit on a light
 * panel (so the lattice inherits navy, exactly like workspace). Both are
 * asserted below — a navy lattice on the navy header would be invisible, and
 * that is a bug no screenshot diff on the light surfaces would ever catch.
 */
const sharedTokensCss = readFileSync(join(process.cwd(), "../../styles/tokens/tokens.css"), "utf8");
const adminGlobalsCss = readFileSync(join(process.cwd(), "src/app/globals.css"), "utf8");
const appBarSource = readFileSync(join(process.cwd(), "src/ui/shell/AppBar.tsx"), "utf8");
const adminShellSource = readFileSync(join(process.cwd(), "src/app/AdminShell.tsx"), "utf8");

describe("brand-mark cross-surface contract", () => {
  it("declares the shared accent-node token in tokens.css", () => {
    expect(sharedTokensCss).toContain("--brand-mark-accent: var(--accent-core);");
  });

  it("has fully retired the gradient-tile tokens", () => {
    expect(sharedTokensCss).not.toContain("--brand-mark-gradient:");
    expect(sharedTokensCss).not.toContain("--font-brand-mark:");
  });
});

describe("admin consumes the shared BrandMark", () => {
  it("imports it from @evidara/shell in both shell surfaces", () => {
    for (const source of [appBarSource, adminShellSource]) {
      expect(source).toContain('import { BrandMark } from "@evidara/shell"');
      expect(source).toContain("<BrandMark");
    }
  });

  it("gives the AppBar mark on-brand colour, not navy, on the dark header", () => {
    // The whole reason BrandMark draws in currentColor. Navy-on-navy = invisible.
    expect(appBarSource).toContain("text-[var(--admin-on-brand)]");
    expect(appBarSource).toContain("[--brand-mark-accent:var(--admin-brand-mark-accent)]");
  });

  it("lifts the accent node off --accent-core for the brand header", () => {
    expect(adminGlobalsCss).toMatch(/--admin-brand-mark-accent:\s*color-mix\([^;]*--accent-core/);
  });

  it("gives the pre-boot shell mark navy, since it sits on a light panel", () => {
    expect(adminGlobalsCss).toMatch(/\.evidara-shell__mark \{[^}]*color:\s*var\(--brand\);/);
  });

  it("does not rebuild the retired gradient tile", () => {
    for (const source of [appBarSource, adminShellSource, adminGlobalsCss]) {
      expect(source).not.toContain("var(--brand-mark-gradient)");
      expect(source).not.toContain("var(--font-brand-mark)");
    }
    expect(adminGlobalsCss).not.toContain(
      "background: linear-gradient(135deg, var(--brand), var(--brand-hover))",
    );
  });
});
