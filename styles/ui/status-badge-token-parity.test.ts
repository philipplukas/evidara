/**
 * `@evidara/ui` shared-primitive brand-token parity.
 *
 * Co-located with the canonical `StatusBadge.tsx` so the parity guard moves
 * with the source. Mirrors the regex/banned-literal pattern from the
 * surface-local parity tests:
 *
 *   - `legal-search/frontend/src/components/primitives/workspace-primitive-token-parity.test.ts`
 *   - `platform-control/admin/src/ui/primitives/admin-primitive-token-parity.test.ts`
 *
 * After this PR, `StatusBadge.tsx` is no longer scanned by either of those
 * tests (they scanned the surface-local copy that is now a re-export shim).
 * This file picks up the coverage so a literal that was scrubbed during the
 * brand-parity track cannot quietly reappear in the shared source.
 *
 * The shared module has no tsconfig project of its own; the test runs
 * inside each surface's vitest because vitest globs `**\/*.test.{ts,tsx}`
 * from `src/`. To keep the canonical scan in one place, both surfaces'
 * `vitest.config.ts` includes this file via the `include` pattern below.
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));

const SCAN_TARGETS = ["StatusBadge.tsx", "status-tokens.ts", "index.ts"] as const;

const sharedSource = SCAN_TARGETS.map((file) =>
  readFileSync(join(here, file), "utf8"),
).join("\n");

describe("@evidara/ui shared primitive brand token parity", () => {
  it("does not introduce raw color literals in the shared primitive layer", () => {
    expect(sharedSource).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    expect(sharedSource).not.toMatch(/rgba?\(\s*\d/);
    expect(sharedSource).not.toMatch(/oklch\(\s*[\d.]/);
    expect(sharedSource).not.toMatch(/hsla?\(\s*\d/);
  });

  it("does not bypass the Tailwind theme via arbitrary color values", () => {
    expect(sharedSource).not.toMatch(
      /(?:bg|text|border|ring|outline|fill|stroke|from|via|to|decoration|caret|accent|placeholder)-\[#[0-9a-fA-F]/,
    );
    expect(sharedSource).not.toMatch(
      /(?:bg|text|border|ring|outline|fill|stroke|from|via|to|decoration|caret|accent|placeholder)-\[rgba?\(/,
    );
    expect(sharedSource).not.toMatch(
      /(?:bg|text|border|ring|outline|fill|stroke|from|via|to|decoration|caret|accent|placeholder)-\[oklch\(/,
    );
    expect(sharedSource).not.toMatch(
      /(?:bg|text|border|ring|outline|fill|stroke|from|via|to|decoration|caret|accent|placeholder)-\[hsla?\(/,
    );
  });

  it("does not reintroduce previously-scrubbed primitive color literals", () => {
    // Mirrors the surface-local parity tests so a literal scrubbed during
    // the brand-parity track cannot quietly reappear in the shared source.
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
      expect(sharedSource).not.toContain(literal);
    }
  });

  it("references the shared status token vocabulary", () => {
    // The shared StatusBadge must be wired into the shared `--status-*`
    // semantic tokens, either through Tailwind utilities (which compile
    // through each surface's `@theme inline` block onto the same CSS vars)
    // or directly as `var(--token)`.
    const hasStatus =
      /status-(?:healthy|degraded|critical|neutral|info)/.test(sharedSource) ||
      /--status-/.test(sharedSource);

    expect(hasStatus).toBe(true);
  });
});
