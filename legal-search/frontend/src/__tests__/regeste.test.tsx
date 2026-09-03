/**
 * Regeste — headnote rendering states
 *
 * WHY THIS TEST EXISTS:
 * The Regeste is the field a lawyer reads first on a Swiss decision, and it was
 * populated in the index and quoted in search snippets while the detail page
 * rendered it nowhere (#760). It is legal text of unbounded length, so the
 * three states that matter are absence, a short headnote, and a long one.
 *
 * WHAT WE TEST:
 * - Nothing at all is rendered when the Regeste is missing or blank — no
 *   labelled box around no text.
 * - A short headnote renders whole, with no expand control.
 * - A long headnote is clamped, expands in place, and the expanded block is
 *   bounded so it cannot push the tabs off the panel.
 * - A11y: no violations, and the toggle reports its state.
 */

import { fireEvent, screen } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { describe, expect, it } from "vitest";
import { Regeste } from "@/components/detail/Regeste";
import { renderWithProviders } from "./helpers/render-with-providers";

expect.extend(toHaveNoViolations);

const SHORT = "Art. 754 OR; Verantwortlichkeit der Verwaltungsratsmitglieder.";

// Two paragraphs, each well past a single clamped line — the shape a real
// Regeste has, and the reason the expand control exists.
const LONG = [
  "Art. 754 OR; Verantwortlichkeit der Verwaltungsratsmitglieder; Beweislastverteilung. Das Bundesgericht bestätigt, dass die Verantwortlichkeit nach Art. 754 OR eine Pflichtverletzung, einen Schaden, einen Kausalzusammenhang und ein Verschulden voraussetzt.",
  "Die Sorgfaltspflicht der Verwaltungsratsmitglieder bemisst sich nach einem objektiven Massstab unter Berücksichtigung der konkreten Umstände des Einzelfalls (E. 4.1).",
].join("\n\n");

describe("Regeste", () => {
  it("renders nothing when there is no Regeste", () => {
    const { container } = renderWithProviders(<Regeste text={undefined} />);
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText("Regeste")).not.toBeInTheDocument();
  });

  it("renders nothing for a whitespace-only Regeste, rather than an empty labelled box", () => {
    const { container } = renderWithProviders(<Regeste text={"   \n\n  "} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders a short headnote whole, with no control that would reveal nothing", () => {
    renderWithProviders(<Regeste text={SHORT} />);

    expect(screen.getByText(SHORT)).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Regeste" })).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("collapses hard-wrapped lines into reflowing paragraphs", () => {
    // Court text in the corpus arrives wrapped mid-sentence; a single newline
    // is a hard wrap, not a paragraph break (see `toParagraphs`).
    renderWithProviders(<Regeste text={"Art. 754 OR;\nVerantwortlichkeit."} />);
    expect(screen.getByText("Art. 754 OR; Verantwortlichkeit.")).toBeInTheDocument();
  });

  it("clamps a long headnote and expands it in place", () => {
    const { container } = renderWithProviders(<Regeste text={LONG} />);

    const prose = container.querySelector("section > div > div");
    expect(prose?.className).toContain("line-clamp-4");

    const toggle = screen.getByRole("button", { name: /Ganze Regeste anzeigen/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    // Both paragraphs are in the DOM either way — the clamp is visual, so the
    // assertion that matters is the container's bound, not the text presence.
    fireEvent.click(toggle);

    expect(prose?.className).not.toContain("line-clamp-4");
    // Bounded and scrollable: an unbounded headnote pushes the tabs off-panel.
    expect(prose?.className).toContain("overflow-y-auto");
    expect(prose?.className).toContain("max-h-[40vh]");
    expect(screen.getByRole("button", { name: /Weniger anzeigen/ })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  it("keeps every paragraph of a long headnote in the document", () => {
    renderWithProviders(<Regeste text={LONG} />);
    expect(screen.getByText(/Beweislastverteilung/)).toBeInTheDocument();
    expect(screen.getByText(/objektiven Massstab/)).toBeInTheDocument();
  });

  it("has no a11y violations, collapsed or expanded", async () => {
    const { container } = renderWithProviders(<Regeste text={LONG} />);
    expect(await axe(container)).toHaveNoViolations();

    fireEvent.click(screen.getByRole("button", { name: /Ganze Regeste anzeigen/ }));
    expect(await axe(container)).toHaveNoViolations();
  });
});
