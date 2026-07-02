/**
 * `@evidara/shell` alias-resolution gate.
 *
 * Mirrors the role of `text-meta-contrast.test.ts` for `@evidara/tokens` —
 * a small unit test whose only job is to fail loudly if the path alias to the
 * monorepo-level shared module breaks (tsconfig + vitest + Next bundler all
 * have to stay aligned with `next.config.ts` `turbopack.root`).
 *
 * Real component imports will replace this once the shell module starts
 * exporting more than a sentinel — see `docs/adr/0028-shared-shell-module.md`.
 */

import { SHELL_MODULE_VERSION } from "@evidara/shell";
import { describe, expect, it } from "vitest";

describe("@evidara/shell alias", () => {
  it("resolves the shared module from the legal-search workspace", () => {
    expect(SHELL_MODULE_VERSION).toBe("0.0.0-scaffold");
  });
});
