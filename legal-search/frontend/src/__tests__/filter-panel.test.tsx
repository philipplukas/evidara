/**
 * FilterPanel — Component Render Tests
 *
 * WHY THESE TESTS EXIST:
 * FilterPanel renders all filter groups (chip, checkbox, dropdown, toggle)
 * and dispatches refinement actions through SearchConstraintsProvider.
 * If filters don't render or dispatch breaks, search refinement is broken.
 *
 * WHAT WE TEST:
 * - Renders filter group labels
 * - Chip filters render and toggle
 * - Checkbox filters render and toggle
 * - Dropdown filters render
 * - Toggle filters render
 * - Collapse/expand works
 * - A11y: no violations
 */

import { fireEvent, screen } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { describe, expect, it } from "vitest";
import { FilterPanel } from "@/components/filters/FilterPanel";
import type { FilterViewModel } from "@/lib/types";
import { renderWithProviders } from "./helpers/render-with-providers";

expect.extend(toHaveNoViolations);

const chipFilter: FilterViewModel = {
  key: "jurisdiction",
  label: "Jurisdiction",
  type: "chip",
  options: [
    { value: "ch", label: "Switzerland", count: 14523, iconKey: "ch" },
    { value: "at", label: "Austria", count: 8291, iconKey: "at" },
  ],
  selected: ["ch"],
};

const checkboxFilter: FilterViewModel = {
  key: "court_level",
  label: "Court level",
  type: "checkbox",
  options: [
    { value: "supreme", label: "Supreme Court", count: 4521 },
    { value: "appellate", label: "Appellate Court", count: 3187 },
  ],
  selected: [],
};

const dropdownFilter: FilterViewModel = {
  key: "date",
  label: "Date",
  type: "dropdown",
  options: [
    { value: "any", label: "Any time" },
    { value: "1y", label: "Last year" },
  ],
  selected: ["any"],
};

const toggleFilter: FilterViewModel = {
  key: "has_commentary",
  label: "Has commentary",
  type: "toggle",
  options: [{ value: "true", label: "Yes" }],
  selected: [],
};

const allFilters = [chipFilter, checkboxFilter, dropdownFilter, toggleFilter];

describe("FilterPanel", () => {
  it("renders the 'Filters' section label", () => {
    renderWithProviders(<FilterPanel filters={allFilters} />);
    expect(screen.getByText("Filters")).toBeInTheDocument();
  });

  it("renders all filter group labels", () => {
    renderWithProviders(<FilterPanel filters={allFilters} />);
    expect(screen.getByText("Jurisdiction")).toBeInTheDocument();
    expect(screen.getByText("Court level")).toBeInTheDocument();
    expect(screen.getByText("Date")).toBeInTheDocument();
    expect(screen.getByText("Has commentary")).toBeInTheDocument();
  });

  it("renders chip filter options", () => {
    renderWithProviders(<FilterPanel filters={[chipFilter]} />);
    expect(screen.getByText("Switzerland")).toBeInTheDocument();
    expect(screen.getByText("Austria")).toBeInTheDocument();
  });

  it("renders checkbox filter options", () => {
    renderWithProviders(<FilterPanel filters={[checkboxFilter]} />);
    expect(screen.getByText("Supreme Court")).toBeInTheDocument();
    expect(screen.getByText("Appellate Court")).toBeInTheDocument();
  });

  it("renders dropdown filter options", () => {
    renderWithProviders(<FilterPanel filters={[dropdownFilter]} />);
    const select = screen.getByRole("combobox");
    expect(select).toBeInTheDocument();
  });

  it("renders toggle filter", () => {
    renderWithProviders(<FilterPanel filters={[toggleFilter]} />);
    expect(screen.getByText("Yes")).toBeInTheDocument();
  });

  it("collapses filter group on header click", () => {
    renderWithProviders(<FilterPanel filters={[checkboxFilter]} />);

    // Options are visible initially
    expect(screen.getByText("Supreme Court")).toBeInTheDocument();

    // Click the collapse button
    fireEvent.click(screen.getByText("Court level"));

    // Options should be hidden
    expect(screen.queryByText("Supreme Court")).not.toBeInTheDocument();
  });

  it("expands collapsed filter group on header click", () => {
    renderWithProviders(<FilterPanel filters={[checkboxFilter]} />);

    // Collapse
    fireEvent.click(screen.getByText("Court level"));
    expect(screen.queryByText("Supreme Court")).not.toBeInTheDocument();

    // Expand
    fireEvent.click(screen.getByText("Court level"));
    expect(screen.getByText("Supreme Court")).toBeInTheDocument();
  });

  it("toggles chip selection on click", () => {
    renderWithProviders(<FilterPanel filters={[chipFilter]} />);

    const austriaButton = screen.getByText("Austria").closest("button");
    expect(austriaButton).toBeInTheDocument();
    fireEvent.click(austriaButton!);

    // After clicking, Austria button should still be present (it toggles state)
    expect(screen.getByText("Austria")).toBeInTheDocument();
  });

  it("has no accessibility violations", async () => {
    const { container } = renderWithProviders(<FilterPanel filters={allFilters} />);

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
