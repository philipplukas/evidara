import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const primitiveFiles = [
  "src/ui/primitives/Button.tsx",
  "src/ui/primitives/Pill.tsx",
  "src/ui/primitives/DataTable.tsx",
  "src/ui/primitives/FormField.tsx",
  "src/ui/primitives/DetailGrid.tsx",
  "src/ui/primitives/Accordion.tsx",
  "src/ui/primitives/Select.tsx",
  "src/ui/primitives/TextInput.tsx",
  "src/ui/shell/Toast.tsx",
];

const primitiveSource = primitiveFiles
  .map((file) => readFileSync(join(process.cwd(), file), "utf8"))
  .join("\n");

describe("admin primitive brand token parity", () => {
  it("uses shared semantic tokens for action, focus, status, and surfaces", () => {
    for (const token of [
      "--accent-core",
      "--focus-ring",
      "--status-healthy",
      "--status-degraded",
      "--status-critical",
      "--status-neutral",
      "--status-info",
      "--surface-panel",
      "--surface-input",
      "--border",
    ]) {
      expect(primitiveSource).toContain(`var(${token})`);
    }
  });

  it("does not reintroduce pre-parity primitive color literals", () => {
    for (const literal of [
      "var(--brand-focus-ring)",
      "text-[#fffdf8]",
      "rgba(15,76,129",
      "rgba(29,41,61",
      "rgba(46,125,50",
      "rgba(237,108,2",
      "rgba(198,40,40",
      "rgba(2,136,209",
      "#b71c1c",
      "#166534",
      "#1e40af",
      "#92400e",
      "#991b1b",
    ]) {
      expect(primitiveSource).not.toContain(literal);
    }
  });
});
