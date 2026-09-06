import { describe, expect, it } from "vitest";
import { formatBuildLabel } from "./build-info";

/**
 * `getBuildInfo` reads module-level constants captured from
 * `process.env.NEXT_PUBLIC_*` at import time — that literal spelling is what makes
 * Next inline the values into the client bundle, and it also means the values
 * cannot be re-read per test. So the env-dependent path is asserted by the source
 * guard at the bottom, and the pure formatting is tested directly here.
 */
describe("formatBuildLabel", () => {
  const base = {
    sha: "4932ec2c29ee31ab591bd9dbb9caa3f59a1e0b13",
    shortSha: "4932ec2c",
    commitUrl: "https://github.com/philipplukas/evidara/commit/4932ec2c",
  };

  it("renders sha and UTC calendar day", () => {
    expect(formatBuildLabel({ ...base, builtAt: "2026-09-06T10:25:00Z" })).toBe(
      "4932ec2c · 2026-09-06",
    );
  });

  it("falls back to the sha alone when no build date was baked", () => {
    expect(formatBuildLabel({ ...base, builtAt: null })).toBe("4932ec2c");
  });

  // Guard: an upstream timestamp-format change must degrade to the SHA, not
  // print a truncated fragment like "4932ec2c · not-a-da".
  it.each([
    "not-a-date",
    "2026-09",
    "",
    "06/09/2026",
  ])("degrades to the sha for unparseable builtAt %s", (builtAt) => {
    expect(formatBuildLabel({ ...base, builtAt })).toBe("4932ec2c");
  });

  it("does not localise the date", () => {
    // A build timestamp is a fact about the release, not about the reader's
    // timezone — two operators comparing notes must read the same string.
    const label = formatBuildLabel({ ...base, builtAt: "2026-09-06T23:59:59Z" });
    expect(label).toContain("2026-09-06");
  });
});

/**
 * Guard for the client-inlining rule. Next.js substitutes `NEXT_PUBLIC_*` into the
 * browser bundle only where it sees the literal member expression at build time;
 * reading it through a variable leaves it `undefined` in the browser and the
 * version silently never renders. A unit test cannot observe the substitution, so
 * assert the source keeps the literals that make it possible — the same technique
 * the admin's `publicConfig.test.ts` uses after that exact bug shipped a 403.
 */
describe("client-inlinable literal references", () => {
  it.each([
    "NEXT_PUBLIC_BUILD_SHA",
    "NEXT_PUBLIC_BUILD_DATE",
  ])("references process.env.%s literally", async (key) => {
    const { readFileSync } = await import("node:fs");
    const { join } = await import("node:path");
    const source = readFileSync(join(__dirname, "build-info.ts"), "utf8");
    expect(source).toContain(`process.env.${key}`);
  });
});
