import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RelatedTab } from "@/components/detail/tabs/RelatedTab";
import { StructureTab } from "@/components/detail/tabs/StructureTab";
import { renderWithProviders } from "./helpers/render-with-providers";

describe("Keyboard interactions", () => {
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

  it("activates structure rows with Space", () => {
    const onFocus = vi.fn();
    renderWithProviders(
      <StructureTab
        onFocus={onFocus}
        items={[
          { id: "art-754", label: "Art. 754 - Liability", active: true },
          { id: "art-755", label: "Art. 755 - Audit", active: false },
        ]}
      />,
    );

    const row = screen.getByRole("button", { name: /Art\. 755 - Audit/ });
    row.focus();
    fireEvent.keyDown(row, { key: " " });

    expect(onFocus).toHaveBeenCalledWith("art-755");
  });
});
