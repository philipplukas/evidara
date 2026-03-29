/**
 * Skeletons — Component Render Tests
 *
 * WHY THESE TESTS EXIST:
 * Skeletons are the first thing users see while content loads.
 * If they crash, users see a white screen instead of a loading state.
 * We also verify a11y patterns for loading indicators.
 *
 * WHAT WE TEST:
 * - Each skeleton renders without crash
 * - ResultListSkeleton renders N skeleton cards
 * - Skeleton base component renders with custom dimensions
 * - A11y: no violations
 */

import { screen } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { describe, expect, it } from "vitest";
import {
  DetailPanelSkeleton,
  FilterPanelSkeleton,
  ResultCardSkeleton,
  ResultListSkeleton,
  Skeleton,
  TextSkeleton,
} from "@/components/skeletons";
import { renderWithProviders } from "./helpers/render-with-providers";

expect.extend(toHaveNoViolations);

describe("Skeleton base", () => {
  it("renders with default styling", () => {
    const { container } = renderWithProviders(<Skeleton />);
    const skeleton = container.querySelector("[class*='animate-pulse']");
    expect(skeleton).toBeInTheDocument();
  });

  it("renders with custom width and height", () => {
    const { container } = renderWithProviders(<Skeleton width="10rem" height="2rem" />);
    const skeleton = container.querySelector("[class*='animate-pulse']");
    expect(skeleton).toBeInTheDocument();
  });
});

describe("TextSkeleton", () => {
  it("renders specified number of lines", () => {
    const { container } = renderWithProviders(<TextSkeleton lines={3} />);
    const lines = container.querySelectorAll("[class*='animate-pulse']");
    expect(lines.length).toBe(3);
  });
});

describe("ResultCardSkeleton", () => {
  it("renders without crash", () => {
    const { container } = renderWithProviders(<ResultCardSkeleton />);
    expect(container.firstChild).toBeInTheDocument();
  });

  it("has no accessibility violations", async () => {
    const { container } = renderWithProviders(<ResultCardSkeleton />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});

describe("ResultListSkeleton", () => {
  it("renders default 6 skeleton cards", () => {
    const { container } = renderWithProviders(<ResultListSkeleton />);
    // Each ResultCardSkeleton has a specific container class
    const cards = container.querySelectorAll(".px-5.py-4.border-b");
    expect(cards.length).toBe(6);
  });

  it("renders custom count of skeleton cards", () => {
    const { container } = renderWithProviders(<ResultListSkeleton count={3} />);
    const cards = container.querySelectorAll(".px-5.py-4.border-b");
    expect(cards.length).toBe(3);
  });
});

describe("DetailPanelSkeleton", () => {
  it("renders without crash", () => {
    const { container } = renderWithProviders(<DetailPanelSkeleton />);
    expect(container.firstChild).toBeInTheDocument();
  });

  it("has no accessibility violations", async () => {
    const { container } = renderWithProviders(<DetailPanelSkeleton />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});

describe("FilterPanelSkeleton", () => {
  it("renders without crash", () => {
    const { container } = renderWithProviders(<FilterPanelSkeleton />);
    expect(container.firstChild).toBeInTheDocument();
  });

  it("has no accessibility violations", async () => {
    const { container } = renderWithProviders(<FilterPanelSkeleton />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
