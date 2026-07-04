import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

// `Pill.tsx` is intentionally absent from this list. Per ADR-0028 the
// status-rendering portion was delegated to the shared `@evidara/ui`
// `StatusBadge` primitive; the admin-local file is a thin adapter whose
// only remaining inline tokens are the neutral `--surface-panel`,
// `--text-meta`, and `--border` for the `meta` variant — already covered
// by other primitives in this scan. The canonical shared source has its
// own token-parity test at `styles/ui/status-badge-token-parity.test.ts`
// (run by the workspace surface's vitest), so coverage is preserved.
const primitiveFiles = [
  "src/ui/primitives/Button.tsx",
  "src/ui/primitives/DataTable.tsx",
  "src/ui/primitives/FormField.tsx",
  "src/ui/primitives/DetailGrid.tsx",
  "src/ui/primitives/InlineAlert.tsx",
  "src/ui/primitives/Panel.tsx",
  "src/ui/primitives/Accordion.tsx",
  "src/ui/primitives/Select.tsx",
  "src/ui/primitives/Spinner.tsx",
  "src/ui/primitives/TextInput.tsx",
  "src/ui/shell/Toast.tsx",
];

const primitiveSource = primitiveFiles
  .map((file) => readFileSync(join(process.cwd(), file), "utf8"))
  .join("\n");

/**
 * Pre-parity color literals — once a brand parity sweep migrates a surface
 * onto `var(--*)` tokens, these literals must not return. Shared between the
 * primitive scope and the resource scope so a future drift gets caught
 * regardless of which file reintroduced it.
 */
const FORBIDDEN_LITERALS = [
  // Brand-strong (`#1d293d`) and brand navy (`#0f4c81`) opacity literals
  // that should route through `--foreground-{muted,subtle,faint,ghost}`,
  // `--border{,-faint,-strong}`, or `--brand-wash-*` instead.
  "rgba(15,76,129",
  "rgba(29,41,61",
  // Material palette rgba leftovers from the v1 react-admin shell.
  "rgba(46,125,50",
  "rgba(237,108,2",
  "rgba(198,40,40",
  "rgba(2,136,209",
  // Material hex literals that should route through `--status-*` / `--attention*`.
  "#b71c1c",
  "#166534",
  "#1e40af",
  "#92400e",
  "#991b1b",
  "#e65100",
] as const;

describe("admin primitive brand token parity", () => {
  it("uses shared semantic tokens for action, focus, status, and surfaces", () => {
    // `--status-neutral` is intentionally absent from this list. The
    // canonical neutral-status rendering moved to the shared `@evidara/ui`
    // `StatusBadge` (per ADR-0028); the workspace and admin surfaces both
    // reach it through Tailwind utilities (`text-status-neutral`,
    // `bg-status-neutral-subtle`) that compile through `@theme inline` →
    // `--status-neutral`. The shared canonical source is guarded by
    // `styles/ui/status-badge-token-parity.test.ts`, so coverage is
    // preserved without forcing every admin primitive to spell the var().
    for (const token of [
      "--accent-core",
      "--focus-ring",
      "--status-healthy",
      "--status-degraded",
      "--status-critical",
      "--status-info",
      "--surface-panel",
      "--surface-input",
      "--border",
    ]) {
      expect(primitiveSource).toContain(`var(${token})`);
    }
  });

  it("does not reintroduce pre-parity primitive color literals", () => {
    for (const literal of ["var(--brand-focus-ring)", "text-[#fffdf8]", ...FORBIDDEN_LITERALS]) {
      expect(primitiveSource).not.toContain(literal);
    }
  });
});

/**
 * Walk `src/resources/` recursively and read every `.tsx` source file.
 * Resource components are operator-facing pages — they routinely shipped
 * raw rgba / Material hex during the v1 → v2 transition. Once a sweep
 * cleans a category, this guard keeps it clean.
 */
function readResourceSource(): { source: string; files: string[] } {
  const root = join(process.cwd(), "src/resources");
  const files: string[] = [];
  const visit = (dir: string): void => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name);
      if (entry.isDirectory()) {
        visit(path);
      } else if (entry.isFile() && entry.name.endsWith(".tsx")) {
        files.push(relative(process.cwd(), path));
      }
    }
  };
  visit(root);
  files.sort();
  const source = files.map((f) => readFileSync(join(process.cwd(), f), "utf8")).join("\n");
  return { source, files };
}

describe("admin resource brand token parity", () => {
  const { source: resourceSource, files: resourceFiles } = readResourceSource();

  it("scans every resource .tsx file (sanity check)", () => {
    expect(resourceFiles.length).toBeGreaterThan(10);
    expect(resourceFiles).toContain("src/resources/runs/RunListV2.tsx");
    expect(resourceFiles).toContain("src/resources/sources/SourceList.tsx");
  });

  it("does not reintroduce pre-parity color literals in resource components", () => {
    for (const literal of FORBIDDEN_LITERALS) {
      expect(resourceSource).not.toContain(literal);
    }
  });
});
