import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FilterPanel } from "@/components/filters/FilterPanel";
import type { FilterViewModel } from "@/lib/types";
import { renderWithProviders } from "./helpers/render-with-providers";

const filters: FilterViewModel[] = [
  {
    key: "jurisdiction",
    label: "Jurisdiction",
    type: "chip",
    options: [
      { value: "ch", label: "Switzerland", count: 10 },
      { value: "at", label: "Austria", count: 8 },
    ],
    selected: ["ch"],
  },
  {
    key: "legal_area",
    label: "Legal area",
    type: "checkbox",
    options: [{ value: "civil", label: "Civil law", count: 5 }],
    selected: [],
  },
  {
    key: "date",
    label: "Date",
    type: "dropdown",
    options: [
      { value: "any", label: "Any time" },
      { value: "1y", label: "Last year" },
    ],
    selected: ["any"],
  },
  {
    key: "has_commentary",
    label: "Has commentary",
    type: "toggle",
    options: [{ value: "true", label: "Yes" }],
    selected: [],
  },
];

describe("FilterPanel interaction matrix", () => {
  it("handles chip, checkbox, dropdown, and toggle interactions", () => {
    renderWithProviders(<FilterPanel filters={filters} />);

    const austriaChip = screen.getByRole("button", { name: /Austria/ });
    fireEvent.click(austriaChip);
    expect(austriaChip.className).toContain("bg-brand-strong");

    const civilCheckbox = screen.getByRole("checkbox", { name: /Civil law/ });
    fireEvent.click(civilCheckbox);
    expect(civilCheckbox.getAttribute("aria-checked")).toBe("true");

    const dateSelect = screen.getByRole("combobox", { name: "Date" });
    fireEvent.change(dateSelect, { target: { value: "1y" } });
    expect((dateSelect as HTMLSelectElement).value).toBe("1y");

    const toggleLabel = screen.getByText("Yes").closest("label");
    const toggleTrack = toggleLabel?.querySelector("div");
    expect(toggleTrack).toBeTruthy();
    fireEvent.click(toggleTrack!);
    expect(toggleTrack?.className).toContain("bg-brand");
  });

  it("supports clear refinements and reset all controls", () => {
    renderWithProviders(<FilterPanel filters={filters} />);

    const clearButton = screen.getByRole("button", { name: /verfeinerungen löschen/i });
    const resetButton = screen.getByRole("button", { name: /alles zurücksetzen/i });
    const austriaChip = screen.getByRole("button", { name: /Austria/ });
    const civilCheckbox = screen.getByRole("checkbox", { name: /Civil law/ });

    expect(clearButton).toBeDisabled();

    fireEvent.click(austriaChip);
    fireEvent.click(civilCheckbox);
    expect(civilCheckbox.getAttribute("aria-checked")).toBe("true");
    expect(clearButton).not.toBeDisabled();

    fireEvent.click(clearButton);
    expect(civilCheckbox.getAttribute("aria-checked")).toBe("false");
    expect(clearButton).toBeDisabled();

    fireEvent.click(resetButton);
    expect(austriaChip.className).not.toContain("bg-brand-strong");
    expect(civilCheckbox.getAttribute("aria-checked")).toBe("false");
  });
});
