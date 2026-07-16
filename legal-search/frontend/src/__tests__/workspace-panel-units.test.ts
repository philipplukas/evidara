/**
 * Panel-size unit guard.
 *
 * react-resizable-panels v4 reads a BARE NUMBER size as PIXELS and a string
 * ("32" / "32%") as a PERCENTAGE. WorkspaceClient's split is authored in
 * percent, so every size that reaches a panel must be a `%` string. The library
 * was added here already at ^4.7.6 — this was never a regression from a working
 * v3; the props were bare numbers from the start, so `resize(32)` and
 * `maxSize={28}` rendered as 32px / 28px, collapsing the detail panel and the
 * filter rail to unusable slivers (the results panel only looked right because
 * it flexes to fill leftover space).
 *
 * SCOPE — read before trusting this file. These are cheap source-text checks
 * that only catch a size written as a LITERAL digit (`minSize={12}`,
 * `resize(32)`). They do NOT catch a bare number arriving via an identifier —
 * `defaultSize={split.filters}`, `minSize={MIN_FILTER}`, `resize(CONST)` all
 * pass this test while reintroducing the bug, and `defaultSize={split.filters}`
 * is precisely one of the forms that shipped it. Rendered geometry is the real
 * guard: see "filter rail and detail panel render at usable widths, not px
 * slivers" in `e2e/workspace-panels.spec.ts`, which measures actual widths.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const workspaceClient = readFileSync(join(process.cwd(), "src/app/WorkspaceClient.tsx"), "utf8");

describe("resizable panel sizes are percentages, not pixels", () => {
  it("never calls resize() with a bare number (v4 would read it as pixels)", () => {
    // Allowed: resize(`${...}%`) or resize("32%"). Forbidden: resize(32).
    expect(workspaceClient).not.toMatch(/\.resize\(\s*\d/);
  });

  it("never passes a bare numeric size prop to a panel", () => {
    // Forbidden: defaultSize={18} / minSize={12} / maxSize={28} / collapsedSize={4}.
    // Allowed: defaultSize={`${split.filters}%`} / minSize="12%".
    expect(workspaceClient).not.toMatch(/(?:defaultSize|minSize|maxSize|collapsedSize)=\{\s*\d/);
  });
});
