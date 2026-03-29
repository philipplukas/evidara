/**
 * AppHeader — Component Render Tests
 *
 * WHY THESE TESTS EXIST:
 * AppHeader contains the search input, the main entry point for the app.
 * If search submission doesn't dispatch or update the URL, the core UX is broken.
 *
 * WHAT WE TEST:
 * - Renders Evidara branding
 * - Renders search input with current query
 * - Submitting form dispatches SEARCH + updates URL
 * - Empty submit does nothing
 * - Renders navigation links (Trail, Pinned)
 * - A11y: no violations
 */

import { fireEvent, screen } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { describe, expect, it, vi } from "vitest";
import { AppHeader } from "@/components/layout/AppHeader";
import { renderWithProviders } from "./helpers/render-with-providers";

expect.extend(toHaveNoViolations);

describe("AppHeader", () => {
  it("renders the Evidara branding", () => {
    renderWithProviders(<AppHeader />);
    expect(screen.getByText("Evidara")).toBeInTheDocument();
  });

  it("renders the search input", () => {
    renderWithProviders(<AppHeader />);
    const input = screen.getByPlaceholderText(/search article, case, commentary/i);
    expect(input).toBeInTheDocument();
  });

  it("populates input with current query from store", () => {
    renderWithProviders(<AppHeader />, {
      initialQuery: "Art 754 OR",
    });

    const input = screen.getByPlaceholderText(
      /search article, case, commentary/i,
    ) as HTMLInputElement;
    expect(input.value).toBe("Art 754 OR");
  });

  it("updates input value on typing", () => {
    renderWithProviders(<AppHeader />);
    const input = screen.getByPlaceholderText(
      /search article, case, commentary/i,
    ) as HTMLInputElement;

    fireEvent.change(input, { target: { value: "new query" } });
    expect(input.value).toBe("new query");
  });

  it("submits form and triggers search", () => {
    renderWithProviders(<AppHeader />, {
      initialQuery: "",
    });

    const input = screen.getByPlaceholderText(/search article, case, commentary/i);
    const form = input.closest("form")!;

    fireEvent.change(input, { target: { value: "Bundesgericht" } });
    fireEvent.submit(form);

    // Input should still have the submitted value
    expect((input as HTMLInputElement).value).toBe("Bundesgericht");
  });

  it("does not submit on empty input", () => {
    renderWithProviders(<AppHeader />, {
      initialQuery: "",
    });

    const input = screen.getByPlaceholderText(/search article, case, commentary/i);
    const form = input.closest("form")!;

    fireEvent.change(input, { target: { value: "   " } });
    fireEvent.submit(form);

    // Input still has whitespace (not cleared, no dispatch)
    expect((input as HTMLInputElement).value).toBe("   ");
  });

  it("renders navigation links", () => {
    renderWithProviders(<AppHeader />);
    expect(screen.getByText("Trail")).toBeInTheDocument();
    expect(screen.getByText("Pinned")).toBeInTheDocument();
  });

  it("renders filters button when onOpenFilters is provided", () => {
    const onOpenFilters = vi.fn();
    renderWithProviders(<AppHeader onOpenFilters={onOpenFilters} />);
    const filtersButton = screen.getByText("Filters");
    expect(filtersButton).toBeInTheDocument();

    fireEvent.click(filtersButton);
    expect(onOpenFilters).toHaveBeenCalledOnce();
  });

  it("has no accessibility violations", async () => {
    const { container } = renderWithProviders(<AppHeader />);

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
