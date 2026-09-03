/**
 * Single-source guard for the shared URL search params (#822).
 *
 * `q`, `item`, `tab`, and the four constraint params are each read by more than
 * one component. When a call site builds its own parser inline —
 * `parseAsString.withDefault("")` — it creates a second default for one param
 * that has to be kept in sync by hand, and it will not be.
 *
 * That shipped twice. #762: `HomeClient` defaulted `q` to the boot query and ran
 * the search, `WorkspaceClient` defaulted it to `""` and rendered "start a
 * search" over those very results. #763 fixed that by sharing the *constant*,
 * not the parser — so `AppHeader` kept its own `parseAsString.withDefault("")`
 * and the third default survived the fix untouched, along with `tab` declared
 * twice in `DetailTabs` and `jurisdictions` / `languages` defaulting to
 * `["CH"]` / `["de"]` in the constraints store while `searchParamsParsers` gave
 * them no default at all (#822).
 *
 * Two checks, because either alone is weak:
 *  - a value check, that the shared parsers really carry the documented
 *    defaults;
 *  - a source-text check, that no file outside `search-params.ts` builds a
 *    parser for one of these params at all. Only the second can see a *new*
 *    divergent call site, which is the failure mode that actually happened —
 *    a value check passes happily while a fifth default is being added.
 */
import { readdirSync, readFileSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";
import {
  DEFAULT_DETAIL_TAB,
  DEFAULT_JURISDICTIONS,
  DEFAULT_LANGUAGES,
  DEFAULT_SEARCH_QUERY,
  searchParamsParsers,
} from "@/lib/search-params";

/** Every param `searchParamsParsers` owns. Nothing else may parse these. */
const OWNED_PARAMS = Object.keys(searchParamsParsers);

const SOURCE_OF_TRUTH = join("src", "lib", "search-params.ts");

function sourceFiles(root: string): string[] {
  const found: string[] = [];

  const walk = (dir: string) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(full);
      } else if (/\.tsx?$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name)) {
        found.push(relative(root, full));
      }
    }
  };

  walk(join(root, "src"));
  return found.filter((file) => file !== SOURCE_OF_TRUTH && !file.includes(`__tests__${sep}`));
}

describe("shared URL search params have exactly one parser each", () => {
  it("resolves the documented defaults from the shared parsers", () => {
    expect(searchParamsParsers.q.parseServerSide(undefined)).toBe(DEFAULT_SEARCH_QUERY);
    expect(searchParamsParsers.tab.parseServerSide(undefined)).toBe(DEFAULT_DETAIL_TAB);
    expect(searchParamsParsers.jurisdictions.parseServerSide(undefined)).toEqual(
      DEFAULT_JURISDICTIONS,
    );
    expect(searchParamsParsers.languages.parseServerSide(undefined)).toEqual(DEFAULT_LANGUAGES);
    expect(searchParamsParsers.officialOnly.parseServerSide(undefined)).toBe(false);
    // Deliberately defaultless — "nothing selected" / "no filter" is a real state.
    expect(searchParamsParsers.item.parseServerSide(undefined)).toBeNull();
    expect(searchParamsParsers.sourceType.parseServerSide(undefined)).toBeNull();
    expect(searchParamsParsers.refinements.parseServerSide(undefined)).toBeNull();
  });

  it("has no call site that builds its own parser for an owned param", () => {
    const root = process.cwd();
    const files = sourceFiles(root);

    expect(files.length, "found no source files to scan — the walk is broken").toBeGreaterThan(20);

    // The parser argument of `useQueryState("q", <parser>)`, captured so it can
    // be compared literally. A negative lookahead would be defeated by `\s*`
    // backtracking to zero width and would pass every call site.
    const singleCall = new RegExp(
      `useQueryState\\(\\s*["'\`](${OWNED_PARAMS.join("|")})["'\`]\\s*,\\s*([^)]+)\\)`,
      "g",
    );
    // `useQueryStates({ jurisdictions: <parser>, … })` — the inline-object form.
    const multiCall = /useQueryStates\(\s*\{([\s\S]*?)\}\s*\)/g;
    const objectEntry = /(?:^|,)\s*(?:["'`])?([A-Za-z_$][\w$]*)(?:["'`])?\s*:\s*([^,]+)/g;

    const offenders: string[] = [];

    for (const file of files) {
      const source = readFileSync(join(root, file), "utf8");

      for (const match of source.matchAll(singleCall)) {
        if (!match[2].trim().startsWith("searchParamsParsers.")) {
          offenders.push(`${file}: useQueryState("${match[1]}", ${match[2].trim()})`);
        }
      }

      for (const match of source.matchAll(multiCall)) {
        for (const entry of match[1].matchAll(objectEntry)) {
          const [, key, value] = entry;
          if (OWNED_PARAMS.includes(key) && !value.trim().startsWith("searchParamsParsers.")) {
            offenders.push(`${file}: useQueryStates({ ${key}: ${value.trim()} })`);
          }
        }
      }
    }

    expect(
      offenders,
      "these call sites build their own parser for a URL param owned by " +
        `${SOURCE_OF_TRUTH} — that is a second default for one param, which is #762/#822. ` +
        "Import the parser (searchParamsParsers.<param>) instead of re-declaring it.",
    ).toEqual([]);
  });

  it("is actually consumed, as its docstring claims", () => {
    // #822's real finding: `searchParamsParsers` and `searchParamsCache` had
    // zero consumers in `src/` while their docstring called them the single
    // source of truth "used by both client hooks and server components".
    const root = process.cwd();
    const consumers = sourceFiles(root).filter((file) =>
      readFileSync(join(root, file), "utf8").includes("searchParamsParsers"),
    );

    expect(consumers.length).toBeGreaterThanOrEqual(4);
  });
});
