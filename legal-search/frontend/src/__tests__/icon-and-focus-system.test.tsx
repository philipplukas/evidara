import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MetadataIcon } from "@/components/primitives";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getIcon, getIconComponent } from "@/lib/icons";

/**
 * One visual system, not three (#694) — and selection ≠ focus (#696).
 *
 * Both defects were invisible to the existing suite because both live in class
 * strings and glyph tables that nothing asserted on. These are the narrowest
 * assertions that fail if either regresses.
 */

const globalsCss = readFileSync(join(process.cwd(), "src/app/globals.css"), "utf8");
const tabsSource = readFileSync(join(process.cwd(), "src/components/ui/tabs.tsx"), "utf8");

// The BFF owns these keys; read them from it rather than restating them, so a
// key added there without a frontend icon fails here instead of rendering
// nothing in production.
const bffIconSource = readFileSync(
  join(process.cwd(), "../api/src/core/presentation/metadata-icons.ts"),
  "utf8",
);
const BFF_META_KEYS = [...bffIconSource.matchAll(/'((?:dtype|meta)-[a-z]+)'/g)].map((m) => m[1]);

/** Colour emoji, regional indicators, and the legacy monochrome text glyphs. */
const NON_LUCIDE_GLYPHS = /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{1F1E6}-\u{1F1FF}]|[§≡●↗✓⚖]/u;

describe("#694 — document-meta icons are one monochrome lucide system", () => {
  it("covers every iconKey the BFF emits", () => {
    // Guards the regex above as much as the map: an empty list would make the
    // per-key assertions below vacuously pass.
    expect(BFF_META_KEYS.length).toBe(10);
    for (const key of BFF_META_KEYS) {
      expect(getIconComponent(key), `${key} has no lucide component`).not.toBeNull();
    }
  });

  it("no longer resolves any meta key to an emoji or text glyph", () => {
    for (const key of BFF_META_KEYS) {
      // Not merely "not an emoji" — the text path must be empty for these keys,
      // so there is exactly one source of truth per key.
      expect(getIcon(key), `${key} still has a text/emoji glyph`).toBeNull();
    }
  });

  it("renders meta keys as themeable svg that inherits currentColor", () => {
    const { container } = render(
      <span className="text-text-meta">
        <MetadataIcon iconKey="meta-language" size={13} />
      </span>,
    );
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(svg?.getAttribute("stroke")).toBe("currentColor");
    expect(container.textContent).not.toMatch(NON_LUCIDE_GLYPHS);
  });

  it("draws the language metadata row with the same mark as the lucide Globe chip", () => {
    // The sharpest instance in #694: ResultCard rendered a lucide <Globe> for
    // the translation chip and 🌐 for `meta-language` a few pixels away.
    const { container } = render(<MetadataIcon iconKey="meta-language" />);
    expect(container.querySelector("svg")?.getAttribute("class")).toContain("lucide-globe");
  });

  it("keeps jurisdiction marks on their own path", () => {
    // Flags stay <img> (a flag has no stroke-icon form) …
    const flag = render(<MetadataIcon iconKey="ch" alt="Switzerland" />);
    expect(flag.getByAltText("Switzerland").getAttribute("src")).toBe("/flags/ch.svg");
    // … and unknown keys fall through to the caller's fallback rather than
    // silently rendering nothing.
    render(<MetadataIcon iconKey="not-a-real-key" fallback={<i data-testid="fb" />} />);
    expect(screen.getByTestId("fb")).toBeTruthy();
  });
});

describe("#696 — keyboard focus is distinguishable from selection", () => {
  it("gives focus its own token, outside the accent-core family", () => {
    expect(globalsCss).toContain("--focus-ring-strong:");
    // The whole defect was that the focus tint was derived from the selection
    // colour. If someone points it back at the accent, this fails.
    const decl = globalsCss.match(/--focus-ring-strong:\s*([^;]+);/)?.[1] ?? "";
    expect(decl).not.toContain("accent-core");
    expect(decl).not.toContain("--ring");
  });

  it("draws focus as an offset outline, never as a border or underline", () => {
    expect(globalsCss).toMatch(/@utility focus-ring-offset/);
    expect(globalsCss).toMatch(/outline:\s*var\(--focus-ring-strong-width\)/);
    expect(globalsCss).toMatch(/outline-offset:\s*var\(--focus-ring-strong-offset\)/);
  });

  it("keeps a visible, non-zero focus indicator — the a11y floor", () => {
    // #696 must never be "fixed" by deleting the indicator.
    const width = globalsCss.match(/--focus-ring-strong-width:\s*([^;]+);/)?.[1]?.trim();
    expect(width).toBeDefined();
    expect(Number.parseFloat(width as string)).toBeGreaterThan(0);
    expect(globalsCss).not.toMatch(/@utility focus-ring-offset[^}]*outline:\s*none/);
  });

  it("stops focus from repainting the border that encodes tab selection", () => {
    // `focus-visible:border-ring` recoloured all four borders, including the
    // `border-b-2` DetailTabs uses for the selected-tab underline.
    expect(tabsSource).not.toContain("focus-visible:border-ring");
    expect(tabsSource).not.toContain("focus-visible:ring-ring");
    expect(tabsSource).not.toContain("focus-visible:outline-ring");

    render(
      <Tabs value="a">
        <TabsList>
          <TabsTrigger value="a" />
        </TabsList>
      </Tabs>,
    );
    const trigger = document.querySelector('[data-slot="tabs-trigger"]');
    expect(trigger?.className).toContain("focus-ring-offset");
    expect(trigger?.className).not.toContain("focus-visible:border-ring");
  });

  it("gives every context-bar control the same focus recipe", () => {
    // The chip and the tab previously had no focus-visible style at all, while
    // both used a ring to mean "selected".
    for (const cls of ["context-bar__official-toggle", "context-bar__chip", "context-bar__tab"]) {
      const block = globalsCss.match(new RegExp(`\\.${cls} \\{([^}]*)\\}`))?.[1] ?? "";
      expect(block, `${cls} has no focus treatment`).toContain("focus-ring-offset");
      expect(block, `${cls} still rings for focus`).not.toContain("focus-visible:ring");
    }
  });
});
