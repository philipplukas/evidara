import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DetailTabs } from "@/components/detail/DetailTabs";
import { articleDetail } from "@/lib/mock-data";
import { renderWithProviders } from "./helpers/render-with-providers";

describe("DetailTabs URL sync (nuqs + Radix)", () => {
  it("defaults to details tab when tab param is absent", () => {
    renderWithProviders(<DetailTabs tabs={articleDetail.tabs} />);

    const details = screen.getByRole("tab", { name: /^Details$/ });
    expect(details).toHaveAttribute("aria-selected", "true");
  });

  it("hydrates active tab from URL search param", () => {
    renderWithProviders(<DetailTabs tabs={articleDetail.tabs} />, {
      searchParams: { tab: "related" },
    });

    expect(screen.getByRole("tab", { name: /Related/ })).toHaveAttribute("aria-selected", "true");
  });

  it("updates selection when user activates another tab", async () => {
    renderWithProviders(<DetailTabs tabs={articleDetail.tabs} />, {
      searchParams: { tab: "related" },
    });

    const detailsTab = screen.getByRole("tab", { name: /^Details$/ });
    fireEvent.mouseDown(detailsTab, { button: 0 });

    await waitFor(() => {
      expect(detailsTab).toHaveAttribute("aria-selected", "true");
    });
  });
});
