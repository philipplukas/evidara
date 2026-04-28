/**
 * Admin shell-level a11y baseline.
 *
 * Mirrors the spirit of `legal-search/frontend/src/__tests__/workspace-client.a11y.test.tsx`
 * (axe assertions on rendered components) for the admin surface. ADR-0027's
 * "Negative" consequences flagged that admin lacked the equivalent of
 * workspace's axe coverage; this is the first installment.
 *
 * Scope is intentionally narrow:
 *   - Stateless primitives that render without ra-core / router providers
 *     (`Button`, `Pill`) — the cross-surface design-system contract.
 *   - `AppBar`, the operator chrome, wrapped in `<MemoryRouter>` so its
 *     `useLocation` hook resolves.
 *
 * Out of scope (tracked separately): full `AppShell` axe coverage, which
 * additionally requires a ra-core notification provider for `ToastAdapter`
 * and a `renderWithAdminProviders` test helper.
 */
import { render } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { Button } from "../ui/primitives/Button";
import { Pill, type PillLevel } from "../ui/primitives/Pill";
import { AppBar } from "../ui/shell/AppBar";

expect.extend(toHaveNoViolations);

describe("admin Button primitive accessibility", () => {
  it("renders all variant + size combinations without axe violations", async () => {
    const { container } = render(
      <div>
        <Button variant="primary" size="sm">
          Promote
        </Button>
        <Button variant="primary" size="md">
          Promote to production
        </Button>
        <Button variant="secondary" size="sm">
          Cancel
        </Button>
        <Button variant="secondary" size="md">
          Save draft
        </Button>
        <Button variant="ghost" size="sm">
          Edit
        </Button>
        <Button variant="ghost" size="md">
          More options
        </Button>
      </div>,
    );

    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("admin Pill primitive accessibility", () => {
  it("renders all status levels without axe violations", async () => {
    const levels: PillLevel[] = ["healthy", "degraded", "critical", "neutral", "info"];
    const { container } = render(
      <div>
        {levels.map((level) => (
          <Pill key={level} level={level}>
            {level}
          </Pill>
        ))}
      </div>,
    );

    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("admin AppBar accessibility", () => {
  it("renders without axe violations on the dashboard route", async () => {
    const { container } = render(
      <MemoryRouter initialEntries={["/"]}>
        <AppBar />
      </MemoryRouter>,
    );

    expect(await axe(container)).toHaveNoViolations();
  });

  it("renders without axe violations on a resource detail route", async () => {
    const { container } = render(
      <MemoryRouter initialEntries={["/runs-v2/run_01"]}>
        <AppBar />
      </MemoryRouter>,
    );

    expect(await axe(container)).toHaveNoViolations();
  });
});
