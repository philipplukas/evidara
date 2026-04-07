import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DetailSheet } from "@/components/layout/DetailSheet";
import { FiltersSheet } from "@/components/layout/FiltersSheet";

vi.mock("@/components/filters/FilterPanel", () => ({
  FilterPanel: () => <div>filter-panel</div>,
}));

vi.mock("@/components/detail/DetailPanel", () => ({
  DetailPanel: () => <div>detail-panel</div>,
}));

describe("Mobile sheet keyboard behavior", () => {
  it("keeps close control focusable and closes filters sheet with Escape", () => {
    const onOpenChange = vi.fn();
    render(<FiltersSheet open={true} onOpenChange={onOpenChange} filters={[]} />);

    const closeButton = screen.getByRole("button", { name: /close/i });
    closeButton.focus();
    expect(closeButton).toHaveFocus();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("keeps close control focusable and closes detail sheet with Escape", () => {
    const onOpenChange = vi.fn();
    render(<DetailSheet open={true} onOpenChange={onOpenChange} detail={null} />);

    const closeButton = screen.getByRole("button", { name: /close/i });
    closeButton.focus();
    expect(closeButton).toHaveFocus();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
