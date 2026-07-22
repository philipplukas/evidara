import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const globalsCss = readFileSync(join(process.cwd(), "src/app/globals.css"), "utf8");
const shellChromeSource = [
  globalsCss,
  readFileSync(join(process.cwd(), "src/ui/shell/AppShell.tsx"), "utf8"),
  readFileSync(join(process.cwd(), "src/ui/shell/AppBar.tsx"), "utf8"),
  readFileSync(join(process.cwd(), "src/ui/shell/SidebarMenu.tsx"), "utf8"),
].join("\n");
const shellComponentSource = [
  readFileSync(join(process.cwd(), "src/ui/shell/AppShell.tsx"), "utf8"),
  readFileSync(join(process.cwd(), "src/ui/shell/AppBar.tsx"), "utf8"),
  readFileSync(join(process.cwd(), "src/ui/shell/SidebarMenu.tsx"), "utf8"),
].join("\n");

describe("admin shell brand tokens", () => {
  it("keeps decorative shell colors behind admin-local CSS variables", () => {
    for (const token of [
      "--admin-page-glow-brand",
      "--admin-page-glow-neutral",
      "--admin-page-top",
      "--admin-page-bottom",
      "--admin-page-sheen-brand",
      "--admin-page-sheen-light",
      "--admin-panel-bg",
      "--admin-on-brand",
      "--admin-header-bg",
      "--admin-header-border",
      "--admin-header-shadow",
      "--admin-shell-header-start",
      "--admin-shell-header-end",
      "--admin-sidebar-bg",
      "--admin-sidebar-bg-strong",
      "--admin-sidebar-footer-bg",
    ]) {
      expect(globalsCss).toContain(`${token}:`);
      expect(shellChromeSource).toContain(`var(${token})`);
    }
  });

  it("does not reintroduce pre-tokenized shell color literals", () => {
    for (const literal of [
      "rgb(15 76 129 / 10%)",
      "rgb(92 107 126 / 8%)",
      "#fbfcfe",
      "#e8eef4",
      "rgb(255 255 255 / 45%)",
      "rgba(255, 253, 248, 0.92)",
      "rgb(15 76 129 / 98%)",
      "rgb(11 61 104 / 94%)",
      "#fffdf8",
      "rgba(13, 58, 98, 0.98)",
      "rgba(9, 48, 83, 0.95)",
      "rgba(29,41,61,0.08)",
      "rgba(255,253,248,0.98)",
      "rgba(248,243,235,0.92)",
      "rgba(98,70,217,0.22)",
    ]) {
      expect(shellChromeSource).not.toContain(literal);
    }
  });

  it("uses the shared focus ring token for shell controls", () => {
    expect(shellComponentSource).toContain("var(--focus-ring)");
    expect(shellComponentSource).not.toContain("var(--brand-focus-ring)");
  });
});

describe("admin shell responsive grid", () => {
  const appShell = readFileSync(join(process.cwd(), "src/ui/shell/AppShell.tsx"), "utf8");

  it("drives the root grid from the responsive class, not a hardcoded inline column", () => {
    // A fixed `288px 1fr` inline at every width reserved the sidebar column on
    // mobile — where the sidebar is an overlay drawer — shoving the header and
    // main content off the right edge. Inline styles can't be overridden by
    // Tailwind responsive classes, so the grid must live in CSS.
    expect(appShell).toContain("admin-app-shell");
    expect(appShell).not.toContain('gridTemplateColumns: "288px 1fr"');
  });

  it("is a single column on mobile and expands to the sidebar column at md", () => {
    expect(globalsCss).toContain(".admin-app-shell");
    // md breakpoint (768px) matches the sidebar's `md:block`.
    expect(globalsCss).toMatch(
      /@media \(min-width: 768px\)[\s\S]*?\.admin-app-shell[\s\S]*?288px 1fr/,
    );
  });

  it("lets the header row grow instead of clipping taller chrome to 80px", () => {
    // A fixed `80px` header track painted the header over the top of `main`
    // wherever the header wrapped taller (63px of overlap at the md breakpoint).
    // The row floors at 80px but grows to fit.
    expect(globalsCss).toMatch(
      /\.admin-app-shell[\s\S]*?grid-template-rows:\s*minmax\(80px,\s*auto\)/,
    );
    expect(globalsCss).not.toMatch(/\.admin-app-shell[\s\S]*?grid-template-rows:\s*80px 1fr/);
  });

  it("stacks the header brand/title/CTA until lg, where the column has room", () => {
    const appBar = readFileSync(join(process.cwd(), "src/ui/shell/AppBar.tsx"), "utf8");
    // Between md (sidebar appears, ~480px content) and lg the three header
    // blocks can't sit side by side without colliding — row layout waits for lg.
    expect(appBar).toContain("lg:flex-row");
    expect(appBar).not.toContain("md:flex-row");
  });

  it("paints the page gradient once instead of tiling it every viewport height", () => {
    // `background-attachment: fixed` sizes the gradient to the viewport, but the
    // `background` shorthand resets `background-repeat` to `repeat` — so every
    // page taller than the window restarted the gradient with a hard seam at
    // exactly one viewport height (#674). Both declarations are load-bearing;
    // dropping either brings the seam back.
    const bodyRule = globalsCss.match(/\nbody \{[\s\S]*?\n\}/g)?.join("\n") ?? "";
    expect(bodyRule).toContain("background-attachment: fixed");
    expect(bodyRule).toContain("background-repeat: no-repeat");
  });
});
