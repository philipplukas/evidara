/**
 * Stylesheet-level guards for the two globals.css changes that are not
 * reachable from jsdom: the button reset, and dark mode.
 *
 * Both are CSS facts, and both were previously *absent* facts — the kind a
 * component test cannot notice. jsdom applies no stylesheet at all, so asserting
 * the rendered colour is impossible; asserting that the rule is in the file is
 * the honest available check, and it is exactly what regressed.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const globalsCss = readFileSync(join(process.cwd(), "src/app/globals.css"), "utf8");
const sharedTokensCss = readFileSync(join(process.cwd(), "../../styles/tokens/tokens.css"), "utf8");

describe("button reset", () => {
  it("neutralises the UA bevel that preflight would have removed", () => {
    // globals.css deliberately imports only Tailwind's theme + utilities
    // layers, so preflight — where the UA button styling is normalised — never
    // ran. Every bare <button>, including the sortable column header on every
    // list, computed `border: 2px outset rgb(0,0,0)`.
    expect(globalsCss).toMatch(/button:not\(\[class\*="Mui"\]\)\s*\{/);
    expect(globalsCss).toContain("border-style: solid");
    expect(globalsCss).toContain("border-width: 0");
  });

  it("scopes the reset away from the residual MUI controls", () => {
    // The whole reason preflight is skipped is that MUI needs its base styles.
    // A reset that also hit `MuiButtonBase-root` would trade one regression for
    // another.
    expect(globalsCss).toContain('button:not([class*="Mui"])');
    expect(globalsCss).not.toMatch(/^\s*button\s*\{/m);
  });

  it("puts the reset in a layer that Tailwind utilities still beat", () => {
    // Unlayered CSS wins over every layer, so an unlayered reset would override
    // `font-semibold` and `px-3` on every button in the app. The explicit layer
    // statement is what orders `base` below `utilities`.
    expect(globalsCss).toContain("@layer theme, base, utilities;");
    expect(globalsCss).toMatch(/@layer base \{[\s\S]*button:not\(\[class\*="Mui"\]\)/);
  });
});

describe("dark mode", () => {
  it("keys off the `dark` class the shared palette already defines", () => {
    // The palette was never the missing piece: tokens.css has carried a
    // complete `.dark` block the whole time and nothing put the class on.
    expect(sharedTokensCss).toContain(".dark {");
    expect(globalsCss).toContain("html.dark");
  });

  it("declares color-scheme for both modes", () => {
    expect(globalsCss).toMatch(/html\s*\{[^}]*color-scheme:\s*light/);
    expect(globalsCss).toMatch(/html\.dark\s*\{[^}]*color-scheme:\s*dark/);
  });

  it("re-points the admin-local header ink and ground for dark", () => {
    // `--admin-on-brand` derives from `--primary-foreground`, which the dark
    // palette flips to near-black for use on light violet buttons — unreadable
    // on the header. `--admin-shell-header-*` derive from `--brand`, which in
    // dark is a light blue meant to be an accent, not a ground.
    const darkBlock = globalsCss.slice(globalsCss.indexOf("html.dark {"));
    for (const token of [
      "--admin-on-brand:",
      "--admin-shell-header-start:",
      "--admin-shell-header-end:",
    ]) {
      expect(darkBlock).toContain(token);
    }
  });
});

describe("no hardcoded surface colours", () => {
  it("keeps `bg-white` out of the components — it does not go dark", () => {
    // AGENTS.md: use `var(--token)`, never a hardcoded colour. Thirteen
    // `bg-white*` call sites stayed white when everything around them went
    // dark; this is the guard that they do not come back.
    const componentSources = [
      "src/resources/runs/RunListV2.tsx",
      "src/resources/runs/RunShowV2.tsx",
      "src/resources/runs/RunDetailSectionsV2.tsx",
      "src/resources/runs/PrimaryDecisionCell.tsx",
      "src/resources/runs/PreviewReviewListV2.tsx",
      "src/resources/corrections/CorrectionsList.tsx",
      "src/resources/corrections/CommentaryInsightList.tsx",
      "src/resources/coverage/AcquisitionCoverageList.tsx",
      "src/resources/sources/SourceVersionDiffPanel.tsx",
      "src/resources/shared/PageContextBar.tsx",
    ]
      .map((file) => readFileSync(join(process.cwd(), file), "utf8"))
      .join("\n");

    expect(componentSources).not.toContain("bg-white");
    expect(componentSources).not.toContain("rgba(255, 253, 248");
  });
});
