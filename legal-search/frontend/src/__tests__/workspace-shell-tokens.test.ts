import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const globalsCss = readFileSync(join(process.cwd(), "src/app/globals.css"), "utf8");

describe("workspace shell styling tokens", () => {
  it("keeps page chrome colors behind workspace-local CSS variables", () => {
    for (const token of [
      "--workspace-page-glow-brand",
      "--workspace-page-glow-neutral",
      "--workspace-page-top",
      "--workspace-page-bottom",
      "--workspace-page-sheen-brand",
      "--workspace-page-sheen-light",
      "--workspace-input-highlight",
    ]) {
      expect(globalsCss).toContain(`${token}:`);
      expect(globalsCss).toContain(`var(${token})`);
    }
  });

  it("does not reintroduce pre-tokenized shell color literals", () => {
    for (const literal of [
      "rgb(15 76 129 / 10%)",
      "rgb(92 107 126 / 8%)",
      "#fbfcfe",
      "#e8eef4",
      "rgb(15 76 129 / 8%)",
      "rgb(255 255 255 / 45%)",
      "rgb(255 255 255 / 60%)",
    ]) {
      expect(globalsCss).not.toContain(literal);
    }
  });
});
