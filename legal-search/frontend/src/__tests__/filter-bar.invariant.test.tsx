import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderWithProviders } from "@/__tests__/helpers/render-with-providers";
import { FilterBar } from "@/components/filters/FilterBar";
import type { FilterViewModel } from "@/lib/types";

const FILTERS: FilterViewModel[] = [
  {
    key: "legal_area",
    label: "Legal area",
    type: "checkbox",
    options: [{ value: "civil", label: "Civil law" }],
    selected: [],
  },
];

describe("FilterBar invariant", () => {
  it("renders nothing when there are no active refinements", () => {
    const { container } = renderWithProviders(<FilterBar filters={FILTERS} />);
    expect(container.firstChild).toBeNull();
  });

  it("shows clear-all when at least one refinement is active", () => {
    renderWithProviders(<FilterBar filters={FILTERS} />, {
      searchParams: {
        refinements: JSON.stringify([{ field: "legal_area", type: "terms", values: ["civil"] }]),
      },
    });

    expect(screen.getByText(/1 aktiver Filter/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /verfeinerungen löschen|clear all|effacer les filtres/i }),
    ).toBeInTheDocument();
  });

  it("hides clear-all row when the last refinement is cleared via chip dismiss", () => {
    const { container } = renderWithProviders(<FilterBar filters={FILTERS} />, {
      searchParams: {
        refinements: JSON.stringify([{ field: "legal_area", type: "terms", values: ["civil"] }]),
      },
    });

    const remove = screen.getByRole("button", { name: /Legal area Filter entfernen/i });
    fireEvent.click(remove);

    expect(container.firstChild).toBeNull();
  });
});
