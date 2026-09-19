import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RelatedTab } from "@/components/detail/tabs/RelatedTab";
import { StructureTab } from "@/components/detail/tabs/StructureTab";
import { FilterPanel } from "@/components/filters/FilterPanel";
import type { FilterViewModel } from "@/lib/types";
import { renderWithProviders } from "./helpers/render-with-providers";

describe("Keyboard interactions", () => {
  const filters: FilterViewModel[] = [
    {
      key: "has_commentary",
      label: "Has commentary",
      type: "toggle",
      options: [{ value: "true", label: "Yes" }],
      selected: [],
    },
  ];

  it("activates related item rows with Enter", () => {
    const onFocus = vi.fn();
    renderWithProviders(
      <RelatedTab
        groups={[
          {
            groupLabel: "Court decisions",
            items: [
              {
                id: "decision-1",
                title: "BGer 4A_123/2022",
                subtitle: "Federal Supreme Court",
              },
            ],
          },
        ]}
        sourceId="law-1"
        onFocus={onFocus}
      />,
    );

    const row = screen.getByRole("button", { name: /BGer 4A_123\/2022/ });
    row.focus();
    fireEvent.keyDown(row, { key: "Enter" });

    expect(onFocus).toHaveBeenCalledWith("decision-1");
  });

  // A structure row activates `onSelectSection`, which moves the reader inside
  // the open document. It used to activate `onFocus` — the workspace's
  // *document* selection — with a `section_id`, which is what made every
  // outline row a 404 (#1040).
  it("activates structure rows with Space", () => {
    const onSelectSection = vi.fn();
    renderWithProviders(
      <StructureTab
        onSelectSection={onSelectSection}
        anchoredIds={new Set(["art-754", "art-755"])}
        items={[
          { id: "art-754", label: "Art. 754 - Liability", active: true },
          { id: "art-755", label: "Art. 755 - Audit", active: false },
        ]}
      />,
    );

    const row = screen.getByRole("button", { name: /Art\. 755 - Audit/ });
    row.focus();
    fireEvent.keyDown(row, { key: " " });

    expect(onSelectSection).toHaveBeenCalledWith("art-755");
  });

  it("toggles filter switch with Enter keyboard activation", () => {
    renderWithProviders(<FilterPanel filters={filters} />);
    const toggle = screen.getByRole("button", { name: "Has commentary toggle" });
    toggle.focus();

    fireEvent.keyDown(toggle, { key: "Enter" });
    fireEvent.keyUp(toggle, { key: "Enter" });

    expect(toggle).toHaveAttribute("aria-pressed", "true");
  });
});
