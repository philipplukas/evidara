import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
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
    expect(austriaChip.className).toContain("bg-accent-core");

    const civilCheckbox = screen.getByRole("checkbox", { name: /Civil law/ });
    fireEvent.click(civilCheckbox);
    expect(civilCheckbox.getAttribute("aria-checked")).toBe("true");

    const dateSelect = screen.getByRole("combobox", { name: "Date" });
    fireEvent.change(dateSelect, { target: { value: "1y" } });
    expect((dateSelect as HTMLSelectElement).value).toBe("1y");

    const toggleTrack = screen.getByRole("button", { name: "Has commentary toggle" });
    expect(toggleTrack).toBeTruthy();
    fireEvent.click(toggleTrack);
    expect(toggleTrack.className).toContain("bg-accent-core");
  });

  it("supports clear refinements and reset all controls", () => {
    renderWithProviders(<FilterPanel filters={filters} />);

    expect(
      screen.queryByRole("button", { name: /verfeinerungen löschen/i }),
    ).not.toBeInTheDocument();

    const resetButton = screen.getByRole("button", { name: /alles zurücksetzen/i });
    const austriaChip = screen.getByRole("button", { name: /Austria/ });
    const civilCheckbox = screen.getByRole("checkbox", { name: /Civil law/ });

    fireEvent.click(austriaChip);
    fireEvent.click(civilCheckbox);
    expect(civilCheckbox.getAttribute("aria-checked")).toBe("true");

    const clearButton = screen.getByRole("button", { name: /verfeinerungen löschen/i });
    fireEvent.click(clearButton);
    expect(civilCheckbox.getAttribute("aria-checked")).toBe("false");
    expect(
      screen.queryByRole("button", { name: /verfeinerungen löschen/i }),
    ).not.toBeInTheDocument();

    fireEvent.click(resetButton);
    expect(austriaChip.className).not.toContain("bg-accent-core");
    expect(civilCheckbox.getAttribute("aria-checked")).toBe("false");
  });
});

/**
 * #610 — dragging the rail below `minSize` collapses it to a ~56px sliver. The
 * panel had no collapsed rendering, so it rendered the *full* panel clipped:
 * a truncated "FILT" heading and orphaned checkbox labels ("S C", "A C").
 */
describe("FilterPanel collapsed rail", () => {
  it("renders an expand affordance instead of clipped filter content", () => {
    renderWithProviders(<FilterPanel filters={filters} collapsed onExpand={() => {}} />);

    expect(screen.getByRole("button", { name: "Filterbereich einblenden" })).toBeInTheDocument();
    // None of the full-panel controls may render into a 56px rail.
    expect(screen.queryByRole("button", { name: /Switzerland/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: /Civil law/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /alles zurücksetzen/i })).not.toBeInTheDocument();
  });

  it("calls onExpand when the rail affordance is activated", () => {
    const onExpand = vi.fn();
    renderWithProviders(<FilterPanel filters={filters} collapsed onExpand={onExpand} />);

    fireEvent.click(screen.getByRole("button", { name: "Filterbereich einblenden" }));
    expect(onExpand).toHaveBeenCalledTimes(1);
  });

  it("renders the full panel when not collapsed", () => {
    renderWithProviders(<FilterPanel filters={filters} />);

    expect(screen.getByRole("button", { name: /Switzerland/ })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Filterbereich einblenden" }),
    ).not.toBeInTheDocument();
  });
});
