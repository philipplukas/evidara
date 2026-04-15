import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MetadataList } from "@/components/detail/MetadataList";
import type { MetadataField } from "@/lib/types";

function fieldsFixture(): MetadataField[] {
  return [
    { label: "Court", value: "Supreme", visibility: "always" },
    { label: "Docket", value: "1", visibility: "default" },
    { label: "Internal", value: "hidden until expanded", visibility: "expanded" },
  ];
}

describe("MetadataList", () => {
  it("shows empty state when there are no fields", () => {
    render(<MetadataList fields={[]} />);
    expect(screen.getByText("No metadata available")).toBeInTheDocument();
  });

  it("compact density shows only always-visible rows", () => {
    render(<MetadataList fields={fieldsFixture()} initialDensity="compact" />);
    expect(screen.getByText("Court")).toBeInTheDocument();
    expect(screen.queryByText("Docket")).not.toBeInTheDocument();
    expect(screen.queryByText("Internal")).not.toBeInTheDocument();
  });

  it("default density shows always and default rows", () => {
    render(<MetadataList fields={fieldsFixture()} initialDensity="default" />);
    expect(screen.getByText("Court")).toBeInTheDocument();
    expect(screen.getByText("Docket")).toBeInTheDocument();
    expect(screen.queryByText("Internal")).not.toBeInTheDocument();
  });

  it("expanded density shows all rows", () => {
    render(<MetadataList fields={fieldsFixture()} initialDensity="expanded" />);
    expect(screen.getByText("Court")).toBeInTheDocument();
    expect(screen.getByText("Docket")).toBeInTheDocument();
    expect(screen.getByText("Internal")).toBeInTheDocument();
  });

  it("expands from default to show hidden fields", () => {
    render(<MetadataList fields={fieldsFixture()} initialDensity="default" />);
    expect(screen.queryByText("Internal")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /show 1 more field/i }));
    expect(screen.getByText("Internal")).toBeInTheDocument();
  });
});
