/**
 * Workspace primitive brand-token parity.
 *
 * Mirrors `platform-control/admin/src/ui/primitives/admin-primitive-token-parity.test.ts`
 * so both surfaces have a CI-enforced floor on token discipline. ADR-0027
 * commits both surfaces to a shared brand (palette, focus ring, status
 * vocabulary); without a parity guard on the workspace side, drift is only
 * visible to a human eyeballing diffs.
 *
 * What this guards:
 *  - No raw color literals (hex, rgb/rgba, oklch, hsl) in the primitive layer.
 *    All color must come through the shared token system, either as a Tailwind
 *    semantic utility (e.g. `text-accent-core`, `bg-status-critical-subtle`)
 *    or as `var(--token)`.
 *  - No Tailwind arbitrary color values (`bg-[#…]`, `text-[rgba(…)]`, …).
 *  - The previously-banned literal set stays banned (mirrored from the admin
 *    test so a literal that was scrubbed from one surface cannot reappear in
 *    the other).
 *
 * Workspace utility classes like `text-accent-core` resolve through the
 * `@theme inline` block in `src/app/globals.css`, which maps Tailwind colors
 * onto the shared CSS custom properties from `styles/tokens/tokens.css`. So a
 * primitive that uses Tailwind utilities is still token-bound; the only thing
 * we need to ban here is bypass syntax.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// `StatusBadge.tsx` is intentionally absent from this list. Per ADR-0028 it
// was promoted to `@evidara/ui` (`styles/ui/StatusBadge.tsx`); the
// workspace-local file is now a re-export shim with no token references of
// its own. The shared canonical source has its own token-parity test at
// `styles/ui/status-badge-token-parity.test.ts` (run by this surface's
// vitest via the `include` glob in `vitest.config.ts`), so coverage is
// preserved without scanning the empty shim here.
const primitiveFiles = [
  "src/components/primitives/AccentButton.tsx",
  "src/components/primitives/ActionTextLink.tsx",
  "src/components/primitives/Badge.tsx",
  "src/components/primitives/DateText.tsx",
  "src/components/primitives/InteractiveRow.tsx",
  "src/components/primitives/SectionLabel.tsx",
  "src/components/ui/badge.tsx",
  "src/components/ui/button.tsx",
  "src/components/ui/button-variants.ts",
  "src/components/ui/input.tsx",
  "src/components/ui/tabs.tsx",
  "src/components/ui/toast.tsx",
];

const primitiveSource = primitiveFiles
  .map((file) => readFileSync(join(process.cwd(), file), "utf8"))
  .join("\n");

describe("workspace primitive brand token parity", () => {
  it("does not introduce raw color literals in the primitive layer", () => {
    expect(primitiveSource).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    expect(primitiveSource).not.toMatch(/rgba?\(\s*\d/);
    expect(primitiveSource).not.toMatch(/oklch\(\s*[\d.]/);
    expect(primitiveSource).not.toMatch(/hsla?\(\s*\d/);
  });

  it("does not bypass the Tailwind theme via arbitrary color values", () => {
    expect(primitiveSource).not.toMatch(
      /(?:bg|text|border|ring|outline|fill|stroke|from|via|to|decoration|caret|accent|placeholder)-\[#[0-9a-fA-F]/,
    );
    expect(primitiveSource).not.toMatch(
      /(?:bg|text|border|ring|outline|fill|stroke|from|via|to|decoration|caret|accent|placeholder)-\[rgba?\(/,
    );
    expect(primitiveSource).not.toMatch(
      /(?:bg|text|border|ring|outline|fill|stroke|from|via|to|decoration|caret|accent|placeholder)-\[oklch\(/,
    );
    expect(primitiveSource).not.toMatch(
      /(?:bg|text|border|ring|outline|fill|stroke|from|via|to|decoration|caret|accent|placeholder)-\[hsla?\(/,
    );
  });

  it("does not reintroduce previously-scrubbed primitive color literals", () => {
    // Mirrors admin-primitive-token-parity.test.ts so a literal scrubbed from
    // one surface cannot quietly reappear in the other.
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
      expect(primitiveSource).not.toContain(literal);
    }
  });

  it("references the shared accent, focus, and status tokens", () => {
    // Either via Tailwind semantic utilities (which compile through @theme inline
    // → CSS vars) or directly as var(--token). We just need to see the surface
    // is wired into each shared concept.
    const hasAccent = /(?:text|bg|border|ring)-accent-core|--accent-core/.test(primitiveSource);
    const hasFocus = /focus-(?:ring|visible)|--focus-ring/.test(primitiveSource);
    const hasStatus =
      /status-(?:healthy|degraded|critical|neutral|info)/.test(primitiveSource) ||
      /--status-/.test(primitiveSource);

    expect(hasAccent).toBe(true);
    expect(hasFocus).toBe(true);
    expect(hasStatus).toBe(true);
  });
});
