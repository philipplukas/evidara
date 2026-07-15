/**
 * Panel-size unit guard.
 *
 * react-resizable-panels v4 reads a BARE NUMBER size as PIXELS and a string
 * ("32" / "32%") as a PERCENTAGE. WorkspaceClient's split is authored in
 * percent, so every size that reaches a panel must be a `%` string. When the
 * library was bumped to v4 the props were still bare numbers, so `resize(32)`
 * and `maxSize={28}` became 32px / 28px — silently collapsing the detail panel
 * and the filter rail to unusable slivers (the results panel only looked right
 * because it flexes to fill leftover space).
 *
 * The neighbouring shell-frame test pins the numeric constants (they still sum
 * to 100) but cannot catch a units regression — it never inspects how they are
 * handed to the panels. This test does, by scanning the source for the
 * bare-number anti-pattern that reintroduces the bug.
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
