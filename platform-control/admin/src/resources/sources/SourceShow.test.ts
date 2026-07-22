/**
 * Empty-value placeholder convention for the admin resource pages (#674).
 *
 * The source detail page rendered the *same field on the same record* two ways:
 * the header pill said "Family: none" while the `Document family` cell in the
 * grid below said "—". Every other admin surface uses the em dash (17 call
 * sites at the time of writing), so the header was the outlier and moved.
 *
 * A source-text assertion rather than a render test: the defect is a copy
 * convention across pages, not the behaviour of one component, and a render
 * test of `SourceShow` would need the whole record/reference-data context to
 * prove one literal.
 */
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const RESOURCES_DIR = join(process.cwd(), "src/resources");

const tsxFilesUnder = (dir: string): string[] =>
  readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) return tsxFilesUnder(full);
    return entry.isFile() && entry.name.endsWith(".tsx") && !entry.name.includes(".test.")
      ? [full]
      : [];
  });

describe("admin empty-value placeholder convention", () => {
  it('renders "Family: —" rather than "Family: none" on the source detail header', () => {
    const sourceShow = readFileSync(join(RESOURCES_DIR, "sources/SourceShow.tsx"), "utf8");

    // Regex rather than a string literal: the source under test is a template
    // literal, and biome's `noTemplateCurlyInString` flags `${` inside a plain
    // string even when the string is the expected value of an assertion.
    expect(sourceShow).toMatch(/Family: \$\{source\.document_family \?\? "—"\}/);
    expect(sourceShow).not.toMatch(/document_family \?\? "none"/);
  });

  it('uses the em dash, never the word "none", for a missing field value', () => {
    const offenders = tsxFilesUnder(RESOURCES_DIR).filter((file) =>
      /\?\?\s*"none"/.test(readFileSync(file, "utf8")),
    );

    expect(offenders).toEqual([]);
  });
});
