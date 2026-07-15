/**
 * Shell frame alignment guard.
 *
 * The workspace is three stacked bars — header, context bar, panel row — that
 * have to read as one column: the search bar must line up with the panel edges
 * directly beneath it. That only holds while all three share one gutter and one
 * max-width, and they previously did not (the header capped at
 * `--container-max` with a 24px gutter, the context bar used 20px, and `<main>`
 * had a 16px gutter and no cap at all — so above 1600px the panels ran
 * full-bleed while the search bar stopped dead).
 *
 * `.shell-frame` in globals.css is now the single owner of those properties.
 * This test asserts all three rows consume it and that none of them re-declare
 * a competing width or gutter.
 *
 * It also pins the desktop panel split, where the failure mode is subtler: a
 * set of sizes that does not total 100 gets renormalized by
 * react-resizable-panels, so the filter rail changes width when the detail
 * panel opens.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { DESKTOP_PANEL_SPLIT } from "@/app/WorkspaceClient";

const read = (path: string) => readFileSync(join(process.cwd(), path), "utf8");

const globalsCss = read("src/app/globals.css");
const appHeader = read("src/components/layout/AppHeader.tsx");
const contextBar = read("src/components/layout/ContextBar.tsx");
const workspaceClient = read("src/app/WorkspaceClient.tsx");

describe("shell frame", () => {
  it("defines the gutter and max-width exactly once, in .shell-frame", () => {
    expect(globalsCss).toContain(".shell-frame {");
    expect(globalsCss).toMatch(
      /\.shell-frame \{\s*@apply mx-auto w-full max-w-\[var\(--container-max\)\] px-4 lg:px-6;/,
    );

    // No other rule may cap width — that is what let the rows drift apart.
    const containerMaxCaps = globalsCss.match(/max-w-\[var\(--container-max\)\]/g) ?? [];
    expect(containerMaxCaps).toHaveLength(1);
  });

  it("frames the header, the context bar, and the panel row on it", () => {
    expect(appHeader).toContain('className="app-header__inner shell-frame"');
    expect(contextBar).toContain('className="context-bar__layout shell-frame"');
    expect(workspaceClient).toMatch(/<main id="main-content" className="shell-frame /);
  });

  it("keeps the framed rules free of their own horizontal padding", () => {
    // Regex-scoped to each rule body so a stray `px-*` cannot creep back in and
    // reintroduce a per-row gutter.
    for (const selector of ["app-header__inner", "context-bar", "context-bar__layout"]) {
      const rule = globalsCss.match(
        new RegExp(`\\.${selector} \\{[^}]*\\}`.replace(/\\\\/g, "\\")),
      );
      expect(rule, `expected a .${selector} rule in globals.css`).not.toBeNull();
      expect(rule?.[0]).not.toMatch(/\bpx-\d/);
      expect(rule?.[0]).not.toMatch(/\bsm:px-\d/);
      expect(rule?.[0]).not.toMatch(/\blg:px-\d/);
    }
  });
});

describe("desktop panel split", () => {
  it.each(
    Object.entries(DESKTOP_PANEL_SPLIT),
  )("totals 100 with the detail panel %s", (_, split) => {
    expect(split.filters + split.results + split.detail).toBe(100);
  });

  it("holds the filter rail at a constant width across both detail states", () => {
    expect(DESKTOP_PANEL_SPLIT.detailOpen.filters).toBe(DESKTOP_PANEL_SPLIT.detailClosed.filters);
  });

  it("collapses the detail panel to zero when nothing is selected", () => {
    expect(DESKTOP_PANEL_SPLIT.detailClosed.detail).toBe(0);
    expect(DESKTOP_PANEL_SPLIT.detailOpen.detail).toBeGreaterThan(0);
  });
});
