import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Guards the ADR-0027 shared-brand contract for the marketing surface.
 *
 * The workspace and admin surfaces each have a parity test that stops
 * hardcoded colour literals reappearing (see
 * `platform-control/admin/src/ui/primitives/admin-primitive-token-parity.test.ts`).
 * Marketing is a third surface consuming the same tokens, so it gets the same
 * guard — otherwise it becomes the soft spot where literals creep back in and
 * the shared palette silently forks three ways.
 *
 * The rule: colour comes from `var(--token)`. Always.
 */

const SRC = path.resolve(__dirname, "..");

/**
 * Hex (#abc / #aabbcc / #aabbccdd), rgb()/rgba(), hsl()/hsla(), oklch().
 *
 * The negative lookahead exempts `#` followed by 1–5 digits, which in this
 * repo is an issue reference (`#680`) rather than a colour — those appear
 * legitimately in comments and in the evidence strings in `content.ts`. The
 * cost is that a purely-numeric 3-to-5-digit hex colour would slip through;
 * six- and eight-digit forms (`#123456`) are still caught, and every colour
 * in the shared palette contains a letter anyway.
 */
const COLOR_LITERAL =
  /(#(?![0-9]{1,5}\b)[0-9a-fA-F]{3,8}\b)|(\brgba?\s*\()|(\bhsla?\s*\()|(\boklch\s*\()/;

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) return walk(full);
    return /\.tsx?$/.test(entry) ? [full] : [];
  });
}

describe("marketing surface token parity", () => {
  const files = walk(SRC).filter((f) => !f.endsWith(".test.ts") && !f.endsWith(".test.tsx"));

  it("finds source files to scan (guards against the walker silently matching nothing)", () => {
    expect(files.length).toBeGreaterThan(3);
  });

  it.each(
    files.map((f) => [path.relative(SRC, f), f] as const),
  )("%s contains no hardcoded colour literals", (_relative, file) => {
    const offending = readFileSync(file, "utf8")
      .split("\n")
      .map((line, index) => [index + 1, line] as const)
      // Evidence strings in content.ts cite file paths with line numbers,
      // never colours; but skip nothing else — comments included, because a
      // literal in a comment is a literal someone will copy.
      .filter(([, line]) => COLOR_LITERAL.test(line));

    expect(
      offending.map(([n, line]) => `${n}: ${line.trim()}`),
      "use var(--token) from styles/tokens/tokens.css instead (ADR-0027)",
    ).toEqual([]);
  });
});
