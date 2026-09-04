/**
 * The icon vocabulary carries exactly one meaning.
 *
 * The defect: in the run queue's STATE column `pending` rendered a ⚠ warning
 * triangle, `running` an ⓘ, `completed` a ✓, `failed` an ⊗. In the *mode* badge
 * in the adjacent column, the same glyph set meant something entirely different
 * — `acceptance` ⚠, `preview` ⓘ, `production` ✓. Two columns, side by side, one
 * glyph set, contradictory meanings: a ⚠ that means "queued" next to a ⚠ that
 * means "this run reaches a live portal".
 *
 * The decision: icons mean lifecycle status and nothing else. Mode keeps its
 * colour — #743 chose `degraded` for `acceptance` deliberately so an
 * unproven-provider run does not read as calmly as a preview — and loses the
 * glyph.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Pill } from "./Pill";

function iconCount(container: HTMLElement): number {
  return container.querySelectorAll("svg").length;
}

describe("Pill variants", () => {
  it("gives a status pill its icon", () => {
    const { container } = render(<Pill level="degraded">pending</Pill>);
    expect(screen.getByText("pending")).toBeTruthy();
    expect(iconCount(container)).toBe(1);
  });

  it("gives a tag the same level colour and NO icon", () => {
    const { container } = render(
      <Pill variant="tag" level="degraded">
        acceptance
      </Pill>,
    );
    const tag = screen.getByText("acceptance");
    expect(iconCount(container)).toBe(0);
    // Same `--status-degraded` ramp as the status badge — the colour is
    // load-bearing (#743), only the glyph goes.
    expect(tag.className).toContain("text-status-degraded");
    expect(tag.className).toContain("bg-status-degraded-subtle");
  });

  it("covers every level, so no mode or status can fall back to an icon", () => {
    for (const level of ["healthy", "degraded", "critical", "neutral", "info"] as const) {
      const { container } = render(
        <Pill variant="tag" level={level}>
          {level}
        </Pill>,
      );
      expect(iconCount(container)).toBe(0);
      expect(screen.getAllByText(level).length).toBeGreaterThan(0);
    }
  });

  it("leaves the neutral meta chip iconless and colourless as before", () => {
    const { container } = render(<Pill variant="meta">website</Pill>);
    expect(iconCount(container)).toBe(0);
    expect(screen.getByText("website").parentElement?.className).toContain("--text-meta");
  });
});
