/**
 * AGPL-3.0 section 13 on the admin surface.
 *
 * Section 13 requires that a user interacting with this software over a network
 * be offered its Corresponding Source. The admin control plane is such a
 * surface, so the source link in `AppBar` is a **licence obligation**, not
 * chrome — deleting it puts the deployment out of compliance, silently, with
 * every other test still green. That is the exact shape of failure AGENTS.md's
 * guard rule exists to prevent, so this file is the guard's test: remove
 * `<RepositoryLink>` from `AppBar.tsx` and every assertion below goes red.
 *
 * The drawn-path assertion is not padding. `legal-search/frontend`'s equivalent
 * (#995) carries the same one because lucide-react v1 exports no `Github`
 * symbol: an icon import that resolves to `undefined` renders an empty anchor
 * that passes a naive "the link exists" check while showing the user nothing.
 *
 * Render harness copied from `admin-shell.a11y.test.tsx` — `AppBar` needs the
 * ra-core context for `useLocation`.
 */
import { REPOSITORY_URL } from "@evidara/shell";
import { render, screen } from "@testing-library/react";
import { CoreAdminContext, testDataProvider } from "ra-core";
import { describe, expect, it } from "vitest";
import { AppShell } from "../ui/shell/AppShell";

function renderShell() {
  return render(
    <CoreAdminContext dataProvider={testDataProvider()}>
      <AppShell>
        <h1>Operator dashboard</h1>
      </AppShell>
    </CoreAdminContext>,
  );
}

describe("AGPL section 13 source link", () => {
  it("offers the source from the admin header, with the mark actually drawn", () => {
    renderShell();

    const link = screen.getByRole("link", { name: "Source code on GitHub" });

    expect(link).toHaveAttribute("href", REPOSITORY_URL);
    expect(link).toHaveAttribute("target", "_blank");

    const rel = link.getAttribute("rel") ?? "";
    expect(rel).toContain("noopener");
    expect(rel).toContain("noreferrer");

    const path = link.querySelector("svg path");
    expect(path).not.toBeNull();
    expect(path?.getAttribute("d") ?? "").not.toHaveLength(0);
  });

  it("points at a real repository URL rather than a placeholder", () => {
    expect(REPOSITORY_URL).toMatch(/^https:\/\/github\.com\/[\w.-]+\/[\w.-]+$/);
  });
});
