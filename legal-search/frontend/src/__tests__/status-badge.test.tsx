import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "@/components/primitives/StatusBadge";
import type { StatusLevel } from "@/lib/status-tokens";

const LEVELS: StatusLevel[] = ["healthy", "degraded", "critical", "neutral", "info"];

describe("StatusBadge", () => {
  it.each(LEVELS)("renders visible label and icon for %s", (status) => {
    const label = `Status ${status}`;
    render(<StatusBadge status={status} label={label} />);

    expect(screen.getByText(label)).toBeInTheDocument();
    const root = screen.getByText(label).closest("span");
    expect(root).toBeTruthy();
    expect(root?.querySelector("svg")).toBeTruthy();
  });

  it("applies md sizing classes when size is md", () => {
    render(<StatusBadge status="healthy" label="OK" size="md" />);
    const root = screen.getByText("OK").closest("span");
    expect(root?.className).toMatch(/text-xs/);
  });
});
