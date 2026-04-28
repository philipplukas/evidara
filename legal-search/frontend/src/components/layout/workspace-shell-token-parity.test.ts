/**
 * Workspace shell brand-token parity.
 *
 * Mirrors `platform-control/admin/src/app/admin-shell-tokens.test.ts` so both
 * surfaces have a CI-enforced floor on token discipline at the shell layer
 * (header, context bar, sheets, dialogs, menus, theme toggle). ADR-0027
 * commits both surfaces to a shared brand (palette, focus ring, surface
 * vocabulary); without a parity guard on the workspace shell, drift is only
 * visible to a human eyeballing diffs.
 *
 * Prior art: PR #482 added the symmetric guardrail at the primitive layer
 * (`src/components/primitives/workspace-primitive-token-parity.test.ts`).
 * This test extends the same discipline upward into shell chrome.
 *
 * What this guards:
 *  - Decorative shell colours stay behind the workspace-local `--workspace-*`
 *    CSS variables defined in `src/app/globals.css`. Each variable must be
 *    both defined in globals.css and consumed somewhere in the shell source
 *    (the layout files OR the `@layer components` rules in globals.css that
 *    those layout files style themselves with).
 *  - The previously-scrubbed literal set (hex codes and rgba triples that
 *    were tokenised away) cannot reappear. Mirrored from the admin shell test
 *    and the PR #482 primitive test.
 *  - The shared focus token `var(--focus-ring)` (or its Tailwind utility
 *    `ring-focus-ring` / `focus-visible:ring-focus-ring`) is the ring source.
 *    The deprecated `var(--brand-focus-ring)` must not reappear.
 *  - Shared semantic tokens `--accent-core` and `--surface-shell` are
 *    consumed by the shell. (Status tokens are intentionally not asserted —
 *    the workspace shell does not render status indicators; that lives in
 *    the result/detail layers.)
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const shellFiles = [
  "src/components/layout/AppHeader.tsx",
  "src/components/layout/ContextBar.tsx",
  "src/components/layout/MobileWorkspace.tsx",
  "src/components/layout/DetailSheet.tsx",
  "src/components/layout/FiltersSheet.tsx",
  "src/components/layout/KeyboardShortcutsDialog.tsx",
  "src/components/layout/PreferencesDialog.tsx",
  "src/components/layout/UserMenu.tsx",
  "src/components/layout/ThemeToggle.tsx",
];

const globalsCss = readFileSync(join(process.cwd(), "src/app/globals.css"), "utf8");
const shellComponentSource = shellFiles
  .map((file) => readFileSync(join(process.cwd(), file), "utf8"))
  .join("\n");
const shellChromeSource = [globalsCss, shellComponentSource].join("\n");

describe("workspace shell brand tokens", () => {
  it("keeps decorative shell colors behind workspace-local CSS variables", () => {
    for (const token of [
      "--workspace-page-glow-brand",
      "--workspace-page-glow-neutral",
      "--workspace-page-top",
      "--workspace-page-bottom",
      "--workspace-page-sheen-brand",
      "--workspace-page-sheen-light",
      "--workspace-input-highlight",
    ]) {
      expect(globalsCss).toContain(`${token}:`);
      expect(shellChromeSource).toContain(`var(${token})`);
    }
  });

  it("does not reintroduce pre-tokenized shell color literals", () => {
    // Mirrors admin-shell-tokens.test.ts and the PR #482 primitive parity
    // test so a literal scrubbed from one surface cannot quietly reappear in
    // another.
    for (const literal of [
      "var(--brand-focus-ring)",
      "text-[#fffdf8]",
      "rgba(15,76,129",
      "rgba(29,41,61",
      "rgba(46,125,50",
      "rgba(237,108,2",
      "rgba(198,40,40",
      "rgba(2,136,209",
      "rgba(98,70,217",
      "#0f4c81",
      "#0F4C81",
      "#6246d9",
      "#6246D9",
      "#b71c1c",
      "#166534",
      "#1e40af",
      "#92400e",
      "#991b1b",
    ]) {
      expect(shellChromeSource).not.toContain(literal);
    }
  });

  it("uses the shared focus ring token for shell controls", () => {
    // Workspace expresses focus rings via the Tailwind utility
    // `ring-focus-ring` (compiled through `@theme inline` →
    // `var(--focus-ring)`), not raw `var(--focus-ring)` calls. Either spelling
    // counts as wired-in; the deprecated `var(--brand-focus-ring)` must not.
    const hasFocusRing =
      /ring-focus-ring/.test(shellComponentSource) ||
      shellComponentSource.includes("var(--focus-ring)");
    expect(hasFocusRing).toBe(true);
    expect(shellComponentSource).not.toContain("var(--brand-focus-ring)");
  });

  it("references the shared accent and shell-surface tokens", () => {
    // Either via Tailwind semantic utilities (which compile through
    // `@theme inline` → CSS vars) or directly as `var(--token)`. We just need
    // to see the shell is wired into each shared concept.
    const hasAccent =
      /(?:text|bg|border|ring)-accent-core/.test(shellComponentSource) ||
      shellChromeSource.includes("var(--accent-core)");
    const hasShellSurface =
      /(?:bg|border)-surface-shell/.test(shellComponentSource) ||
      shellChromeSource.includes("var(--surface-shell)");

    expect(hasAccent).toBe(true);
    expect(hasShellSurface).toBe(true);
  });
});
