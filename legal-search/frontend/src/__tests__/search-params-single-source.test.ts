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
 * The source-text check below rejects any `useQueryState` / `useQueryStates`
 * call site in `src/` whose parser is not *literally* `searchParamsParsers.<x>`.
 * A chained `searchParamsParsers.q.withDefault("")` is rejected too: that is a
 * one-line restoration of the exact defect this guard exists to prevent, and a
 * `startsWith` check would wave it through.
 *
 * Three evasions were tried against it and all three fail the suite: a chained
 * `searchParamsParsers.q.withDefault("")`, a non-literal key
 * (`useQueryState(Q_PARAM, parseAsString.withDefault(""))`), and a hoisted
 * parser map (`useQueryStates(LOCAL_PARSERS)`). The key is not required to be a
 * string literal — `EXEMPT_PARAMS` names the params that legitimately parse
 * elsewhere, so anything else is an offender however it is spelled.
 *
 * **What it does not chase.** It reads source text, so it cannot follow a
 * renamed import (`import { searchParamsParsers as sp }` … `sp.q`). This is a
 * lint, not a type system: it closes the path a divergence actually arrives by
 * — copy a `useQueryState` line, tweak the default — not every path an author
 * determined to evade it could take.
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

const SOURCE_OF_TRUTH = join("src", "lib", "search-params.ts");

/**
 * Params that may be parsed outside `search-params.ts`.
 *
 * `locale` only: its default is resolved at runtime from `localStorage` /
 * `navigator` (`src/lib/locale-context.tsx`), so it cannot live in a module
 * that `nuqs/server` and Server Components import. It has one call site.
 */
const EXEMPT_PARAMS = new Set(["locale"]);

/** Exactly `searchParamsParsers.<name>` — no chained `.withDefault(...)`. */
const SHARED_PARSER = /^searchParamsParsers\.[A-Za-z_$][\w$]*$/;

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

/** Split `text` on commas that are not nested inside (), {} or []. */
function splitTopLevel(text: string): string[] {
  const parts: string[] = [];
  let depth = 0;
  let current = "";

  for (const char of text) {
    if (char === "(" || char === "{" || char === "[") depth++;
    else if (char === ")" || char === "}" || char === "]") depth--;

    if (char === "," && depth === 0) {
      parts.push(current.trim());
      current = "";
      continue;
    }
    current += char;
  }

  if (current.trim()) parts.push(current.trim());
  return parts;
}

/**
 * Top-level arguments of every `hook(...)` call in `source`.
 *
 * Bracket-balanced rather than regex-matched: a regex either stops at the first
 * `)` — truncating an inline parser map — or backtracks to zero width and
 * matches everything, and both failures read as "no offenders".
 */
function callArguments(source: string, hook: string): string[][] {
  const calls: string[][] = [];
  const needle = `${hook}(`;

  for (let at = source.indexOf(needle); at !== -1; at = source.indexOf(needle, at + 1)) {
    // `foo.useQueryState(` / `myUseQueryState(` are not this hook.
    const before = source[at - 1];
    if (before && /[\w$.]/.test(before)) continue;

    let depth = 0;
    let body = "";

    for (let i = at + needle.length - 1; i < source.length; i++) {
      const char = source[i];
      if (char === "(" || char === "{" || char === "[") {
        depth++;
        if (depth === 1) continue;
      } else if (char === ")" || char === "}" || char === "]") {
        depth--;
        if (depth === 0) break;
      }
      body += char;
    }

    calls.push(splitTopLevel(body));
  }

  return calls;
}

/** `"q"` / `'q'` / `` `q` `` → `q`; anything else (an identifier) → null. */
function stringLiteral(expression: string): string | null {
  const match = /^(["'`])(.*)\1$/.exec(expression.trim());
  return match ? match[2] : null;
}

describe("shared URL search params have exactly one parser each", () => {
  it("resolves the documented defaults from the shared parsers", () => {
    expect(searchParamsParsers.q.parseServerSide(undefined)).toBe(DEFAULT_SEARCH_QUERY);
    expect(searchParamsParsers.tab.parseServerSide(undefined)).toBe(DEFAULT_DETAIL_TAB);
    // These two only pin the parser to the constant. What pins the *constant*
    // to reality is `search-constraints.test.tsx`, which asserts the store
    // reports the same values on a cold URL — without that the pair below is
    // a tautology.
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

  it("keeps a searched query in the URL even when it equals the default", () => {
    // nuqs deletes a param whose written value equals the parser default
    // (`clearOnDefault`, on by default). For `q` that would strip the address
    // bar of the very query the user just ran, so the link they copy resolves
    // to whatever `DEFAULT_SEARCH_QUERY` is when it is opened. See the
    // behavioural half of this in `app-header.test.tsx`.
    expect(searchParamsParsers.q.clearOnDefault).toBe(false);
  });

  it("has no call site that builds its own parser for a shared param", () => {
    const root = process.cwd();
    const files = sourceFiles(root);

    expect(files.length, "found no source files to scan — the walk is broken").toBeGreaterThan(20);

    const offenders: string[] = [];

    for (const file of files) {
      const source = readFileSync(join(root, file), "utf8");

      for (const [key, parser] of callArguments(source, "useQueryState")) {
        if (parser === undefined) continue;
        const param = stringLiteral(key);
        if (param !== null && EXEMPT_PARAMS.has(param)) continue;
        if (!SHARED_PARSER.test(parser)) {
          offenders.push(`${file}: useQueryState(${key}, ${parser})`);
        }
      }

      for (const [keyMap] of callArguments(source, "useQueryStates")) {
        if (keyMap === undefined) continue;
        // `useQueryStates` takes one object. A hoisted binding arrives here as
        // a bare identifier, and the parsers it holds cannot be checked — so it
        // is an offender rather than a pass.
        if (!keyMap.startsWith("{") || !keyMap.endsWith("}")) {
          offenders.push(`${file}: useQueryStates(${keyMap}) — parser map is not inline`);
          continue;
        }
        for (const entry of splitTopLevel(keyMap.slice(1, -1))) {
          const separator = entry.indexOf(":");
          if (separator === -1) continue;
          const key = entry
            .slice(0, separator)
            .trim()
            .replace(/^["'`]|["'`]$/g, "");
          const parser = entry.slice(separator + 1).trim();
          if (EXEMPT_PARAMS.has(key)) continue;
          if (!SHARED_PARSER.test(parser)) {
            offenders.push(`${file}: useQueryStates({ ${key}: ${parser} })`);
          }
        }
      }
    }

    expect(
      offenders,
      "these call sites build their own parser for a URL search param instead of using " +
        `searchParamsParsers from ${SOURCE_OF_TRUTH} — that is a second default for one ` +
        "param, which is #762/#822. Pass searchParamsParsers.<param> unchained, or add the " +
        "param to EXEMPT_PARAMS with a reason.",
    ).toEqual([]);
  });

  it("is actually imported, as its docstring claims", () => {
    // #822's real finding: `searchParamsParsers` and `searchParamsCache` had
    // zero consumers in `src/` while the module docstring called itself the
    // single source of truth "used by both client hooks and server components".
    // Counted from import statements, not raw occurrences — a mention in a
    // comment is not a consumer.
    const root = process.cwd();
    const importsParsers =
      /import\s*\{[^}]*\bsearchParamsParsers\b[^}]*\}\s*from\s*["'][^"']*search-params["']/;
    const consumers = sourceFiles(root).filter((file) =>
      importsParsers.test(readFileSync(join(root, file), "utf8")),
    );

    expect(consumers.sort()).toEqual(
      [
        join("src", "app", "HomeClient.tsx"),
        join("src", "app", "WorkspaceClient.tsx"),
        join("src", "components", "detail", "DetailTabs.tsx"),
        join("src", "components", "layout", "AppHeader.tsx"),
        join("src", "lib", "search-constraints-store.tsx"),
      ].sort(),
    );
  });
});
