/**
 * Smoke test for the admin jsdom + React Testing Library harness.
 *
 * This is intentionally narrow — it proves that `vitest.config.ts` is wired
 * to jsdom, that `@testing-library/jest-dom` matchers register, and that a
 * tsx component can render under `@testing-library/react`. Behavioural
 * coverage for `PrimaryDecisionCell` (and the wider RunShow hierarchy)
 * belongs in follow-up tests once the harness exists.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PrimaryDecisionCell } from "./PrimaryDecisionCell";

describe("PrimaryDecisionCell", () => {
  it("renders the label and value", () => {
    render(<PrimaryDecisionCell label="Why this matters" value="Production source is failing." />);

    expect(screen.getByText("Why this matters")).toBeInTheDocument();
    expect(screen.getByText("Production source is failing.")).toBeInTheDocument();
  });

  it("applies the elevated `--shadow-card-hover` token so it reads as the primary cue", () => {
    const { container } = render(
      <PrimaryDecisionCell label="Why this matters" value="Production source is failing." />,
    );

    // The elevated shadow token is what distinguishes the primary cell from
    // the subordinate `DecisionCell` quadrants (issue #393).
    expect(container.firstChild).toHaveClass("shadow-[var(--shadow-card-hover)]");
  });
});
