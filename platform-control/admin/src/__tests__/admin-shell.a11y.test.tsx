/**
 * Shell-level axe coverage for the admin surface.
 *
 * Mirrors `legal-search/frontend/src/__tests__/workspace-client.a11y.test.tsx`
 * so the cross-surface accessibility non-negotiables called out in
 * ADR-0027 — identical WCAG AA contrast, identical focus-ring affordance,
 * identical accessible-name conventions — are enforced symmetrically.
 *
 * Renders `<AppShell>` inside `CoreAdminContext` so `useResourceDefinitions`,
 * `useLocation`, and the rest of the ra-core hooks the chrome depends on
 * resolve. The shell is exercised with the default (preview) extra items so
 * the sidebar's resource-empty + extra-items branch is also covered.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { CoreAdminContext, testDataProvider } from "ra-core";
import { describe, expect, it, vi } from "vitest";
import { AppShell } from "../ui/shell/AppShell";

expect.extend(toHaveNoViolations);

function renderShell() {
  return render(
    <CoreAdminContext dataProvider={testDataProvider()}>
      <AppShell>
        <h1>Operator dashboard</h1>
        <p>Static content used to exercise the shell chrome under axe.</p>
      </AppShell>
    </CoreAdminContext>,
  );
}

describe("AppShell route-level accessibility", () => {
  it("has no accessibility violations in the default chrome state", async () => {
    const { container } = renderShell();

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});

describe("AppShell mobile drawer keyboard exit", () => {
  const drawer = () => screen.queryByRole("complementary", { name: "Primary navigation" });

  it("closes on Escape", () => {
    renderShell();
    fireEvent.click(screen.getByRole("button", { name: "Open navigation" }));
    expect(drawer()).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });

    expect(drawer()).not.toBeInTheDocument();
  });

  it("ignores other keys", () => {
    renderShell();
    fireEvent.click(screen.getByRole("button", { name: "Open navigation" }));

    fireEvent.keyDown(document, { key: "a" });

    expect(drawer()).toBeInTheDocument();
  });

  it("detaches the key listener once closed", () => {
    renderShell();
    const add = vi.spyOn(document, "addEventListener");
    const remove = vi.spyOn(document, "removeEventListener");

    fireEvent.click(screen.getByRole("button", { name: "Open navigation" }));
    expect(add).toHaveBeenCalledWith("keydown", expect.any(Function));

    fireEvent.keyDown(document, { key: "Escape" });
    expect(remove).toHaveBeenCalledWith("keydown", expect.any(Function));
  });
});
