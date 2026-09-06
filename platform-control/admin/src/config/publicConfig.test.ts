import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";
import { buildPublicConfig, DEFAULT_LEGAL_SEARCH_BASE_URL } from "./publicConfig";

describe("publicConfig", () => {
  describe("minioConsoleBaseUrl", () => {
    it("is undefined when unset, with no default origin", () => {
      expect(buildPublicConfig({}).minioConsoleBaseUrl).toBeUndefined();
    });

    it("is undefined when only whitespace", () => {
      expect(
        buildPublicConfig({ NEXT_PUBLIC_MINIO_CONSOLE_URL: "   " }).minioConsoleBaseUrl,
      ).toBeUndefined();
    });

    it("trims surrounding whitespace but leaves the path alone", () => {
      // Trailing-slash normalization is deliberately NOT here — it belongs to
      // the URL builders (`runDeepLinks.normalizeBase`), so this stays a
      // faithful record of what was configured.
      expect(
        buildPublicConfig({ NEXT_PUBLIC_MINIO_CONSOLE_URL: "  https://minio.example/  " })
          .minioConsoleBaseUrl,
      ).toBe("https://minio.example/");
    });
  });

  /**
   * Boundary guard. `publicConfig`'s stated rule is that app code imports
   * canonical names and never reads `process.env.NEXT_PUBLIC_*` directly — but
   * nothing enforced it, and three call sites had drifted
   * (`ui/shell/SidebarMenu.tsx`, `ui/shell/AppBar.tsx`,
   * `resources/runs/RunDetailSectionsV2.tsx`), two of them with their own
   * hardcoded `http://localhost:3101` fallback. That is the "same rule enforced
   * in two clients" failure: the ad-hoc read becomes the real policy, and it is
   * the weaker one, because only this module's literal snapshot actually
   * reaches the client bundle.
   *
   * Delete the fix in any of those files and this test goes red.
   */
  describe("no direct NEXT_PUBLIC_* reads outside this module", () => {
    const srcDir = join(__dirname, "..");
    // `middleware.ts` is the documented framework-boundary exception, and it
    // reads a server-only var rather than a NEXT_PUBLIC_* one anyway.
    const allowed = new Set(["config/publicConfig.ts", "middleware.ts"]);

    function walk(dir: string): string[] {
      return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
        const full = join(dir, entry.name);
        if (entry.isDirectory()) {
          return entry.name === "node_modules" ? [] : walk(full);
        }
        return /\.tsx?$/.test(entry.name) ? [full] : [];
      });
    }

    it("finds none", () => {
      const offenders = walk(srcDir)
        .filter((file) => !file.endsWith(".test.ts") && !file.endsWith(".test.tsx"))
        .filter((file) => /process\.env\.NEXT_PUBLIC_/.test(readFileSync(file, "utf8")))
        .map((file) => relative(srcDir, file))
        .filter((rel) => !allowed.has(rel));

      expect(offenders).toEqual([]);
    });
  });

  describe("legalSearchBaseUrl", () => {
    it("falls back to the local default when unset", () => {
      expect(buildPublicConfig({}).legalSearchBaseUrl).toBe(DEFAULT_LEGAL_SEARCH_BASE_URL);
    });

    it("falls back when the value is only whitespace", () => {
      expect(buildPublicConfig({ NEXT_PUBLIC_LEGAL_SEARCH_URL: "   " }).legalSearchBaseUrl).toBe(
        DEFAULT_LEGAL_SEARCH_BASE_URL,
      );
    });

    it("trims surrounding whitespace from the configured value", () => {
      expect(
        buildPublicConfig({ NEXT_PUBLIC_LEGAL_SEARCH_URL: "  https://ls.example/  " })
          .legalSearchBaseUrl,
      ).toBe("https://ls.example/");
    });
  });

  describe("legalSearchBaseUrlOrUndefined", () => {
    it("is undefined when unset (distinguishing unconfigured from default)", () => {
      expect(buildPublicConfig({}).legalSearchBaseUrlOrUndefined).toBeUndefined();
    });

    it("is undefined when whitespace-only", () => {
      expect(
        buildPublicConfig({ NEXT_PUBLIC_LEGAL_SEARCH_URL: "   " }).legalSearchBaseUrlOrUndefined,
      ).toBeUndefined();
    });

    it("returns the trimmed value when configured", () => {
      expect(
        buildPublicConfig({ NEXT_PUBLIC_LEGAL_SEARCH_URL: "  https://ls.example/  " })
          .legalSearchBaseUrlOrUndefined,
      ).toBe("https://ls.example/");
    });
  });

  describe("defaultUserRole", () => {
    it("is undefined when unset", () => {
      expect(buildPublicConfig({}).defaultUserRole).toBeUndefined();
    });

    it("returns the raw value untrimmed so `normalizeRole` owns normalization", () => {
      expect(buildPublicConfig({ NEXT_PUBLIC_USER_ROLE: "  Admin " }).defaultUserRole).toBe(
        "  Admin ",
      );
    });
  });

  describe("adminAllowedRoles", () => {
    it("defaults to ['admin'] when unset", () => {
      expect(buildPublicConfig({}).adminAllowedRoles).toEqual(["admin"]);
    });

    it("splits, trims, and lowercases comma-separated values", () => {
      expect(
        buildPublicConfig({ NEXT_PUBLIC_ADMIN_ALLOWED_ROLES: "Admin, Operator ,VIEWER" })
          .adminAllowedRoles,
      ).toEqual(["admin", "operator", "viewer"]);
    });

    it("filters empty entries produced by trailing or duplicate commas", () => {
      expect(
        buildPublicConfig({ NEXT_PUBLIC_ADMIN_ALLOWED_ROLES: "admin, ,,operator," })
          .adminAllowedRoles,
      ).toEqual(["admin", "operator"]);
    });

    it("returns an empty list when the env var is explicitly empty (?? treats '' as set)", () => {
      // Preserves the historical `parseAllowedRoles(env ?? "admin")` behavior:
      // an explicit empty string keeps the empty list, which the consumer
      // interprets as "allow all" via its `effectiveAllowedRoles` fallback.
      expect(buildPublicConfig({ NEXT_PUBLIC_ADMIN_ALLOWED_ROLES: "" }).adminAllowedRoles).toEqual(
        [],
      );
    });

    it("returns an empty list when the env var contains only separators/whitespace", () => {
      expect(
        buildPublicConfig({ NEXT_PUBLIC_ADMIN_ALLOWED_ROLES: " , , " }).adminAllowedRoles,
      ).toEqual([]);
    });
  });

  /**
   * Regression guard for the client-side inlining bug (403 access-denied on
   * the deployed admin). Next.js only substitutes `NEXT_PUBLIC_*` into the
   * *client* bundle when the source contains the literal member expression
   * `process.env.NEXT_PUBLIC_FOO`. The module-level `publicConfig` must build
   * from such literals; reading them dynamically (`env.NEXT_PUBLIC_FOO`) leaves
   * every value `undefined` in the browser and breaks the access gate. A unit
   * test can't observe Turbopack's substitution, so we assert the source keeps
   * the literal references that make it possible.
   */
  describe("client-inlinable literal references (regression: admin 403)", () => {
    const source = readFileSync(join(__dirname, "publicConfig.ts"), "utf8");

    for (const key of [
      "NEXT_PUBLIC_LEGAL_SEARCH_URL",
      "NEXT_PUBLIC_MINIO_CONSOLE_URL",
      "NEXT_PUBLIC_USER_ROLE",
      "NEXT_PUBLIC_ADMIN_ALLOWED_ROLES",
    ]) {
      it(`references process.env.${key} literally so Next inlines it into the client bundle`, () => {
        expect(source).toContain(`process.env.${key}`);
      });
    }
  });
});
