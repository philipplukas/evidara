/**
 * `@evidara/ui` alias-resolution gate.
 *
 * Mirrors `shell-alias.test.ts` (added in PR #502 for `@evidara/shell`) and
 * `text-meta-contrast.test.ts` (which gates `@evidara/tokens`) — a small
 * unit test whose only job is to fail loudly if the path alias to the
 * monorepo-level `styles/ui/` module breaks. tsconfig + vitest + Next
 * bundler all have to stay aligned with `next.config.ts` `turbopack.root`.
 *
 * See `docs/adr/0028-shared-shell-module.md` and `styles/ui/README.md`.
 */

import { StatusBadge, UI_MODULE_VERSION } from "@evidara/ui";
import { describe, expect, it } from "vitest";

describe("@evidara/ui alias", () => {
  it("resolves the shared module from the legal-search workspace", () => {
    expect(UI_MODULE_VERSION).toBe("0.1.0-status-badge");
  });

  it("exposes the canonical StatusBadge component", () => {
    expect(typeof StatusBadge).toBe("function");
  });
});
