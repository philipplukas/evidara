/**
 * DetailPanel — Component Render Tests
 *
 * WHY THESE TESTS EXIST:
 * DetailPanel is the primary document view. If it fails to render,
 * users cannot inspect any search result.
 *
 * WHAT WE TEST:
 * - Shows empty state when detail is null
 * - Renders title, breadcrumbs, metadata when detail is provided
 * - A11y: no violations
 */

import { screen } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { describe, expect, it, vi } from "vitest";
import { DetailPanel } from "@/components/detail/DetailPanel";
import { articleDetail } from "@/lib/mock-data";
import { renderWithProviders } from "./helpers/render-with-providers";

expect.extend(toHaveNoViolations);

describe("DetailPanel", () => {
  it("shows empty state when detail is null", () => {
    renderWithProviders(<DetailPanel detail={null} />);

    expect(screen.getByText("Select a result")).toBeInTheDocument();
    expect(screen.getByText(/Click on a search result to view its details/)).toBeInTheDocument();
  });

  it("renders title and subtitle when detail is provided", () => {
    renderWithProviders(
      <DetailPanel
        detail={articleDetail}
        onFocus={vi.fn()}
        onPivot={vi.fn()}
        onPin={vi.fn()}
        isPinned={false}
      />,
    );

    expect(screen.getByText("Art. 754 OR")).toBeInTheDocument();
    expect(
      screen.getByText("Verantwortlichkeit — Haftung der Verwaltung und der Geschäftsführung"),
    ).toBeInTheDocument();
  });

  it("renders tab labels", () => {
    renderWithProviders(
      <DetailPanel
        detail={articleDetail}
        onFocus={vi.fn()}
        onPivot={vi.fn()}
        onPin={vi.fn()}
        isPinned={false}
      />,
    );

    expect(screen.getByText("Details")).toBeInTheDocument();
    expect(screen.getByText("Related")).toBeInTheDocument();
    expect(screen.getByText("References")).toBeInTheDocument();
    expect(screen.getByText("Annotation")).toBeInTheDocument();
    expect(screen.getByText("Structure")).toBeInTheDocument();
  });

  it("renders metadata rows", () => {
    renderWithProviders(
      <DetailPanel
        detail={articleDetail}
        onFocus={vi.fn()}
        onPivot={vi.fn()}
        onPin={vi.fn()}
        isPinned={false}
      />,
    );

    expect(screen.getByText("Switzerland")).toBeInTheDocument();
    expect(screen.getByText("Obligationenrecht (OR)")).toBeInTheDocument();
  });

  it("has no accessibility violations (empty state)", async () => {
    const { container } = renderWithProviders(<DetailPanel detail={null} />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("has no accessibility violations (with detail)", async () => {
    const { container } = renderWithProviders(
      <DetailPanel
        detail={articleDetail}
        onFocus={vi.fn()}
        onPivot={vi.fn()}
        onPin={vi.fn()}
        isPinned={false}
      />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
