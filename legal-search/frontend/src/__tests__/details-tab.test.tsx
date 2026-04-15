import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DetailsTab } from "@/components/detail/tabs/DetailsTab";
import type { DetailViewModel } from "@/lib/types";
import { renderWithProviders } from "./helpers/render-with-providers";

function buildDetail(
  contentHtml: string,
  metadata: DetailViewModel["metadata"] = [],
): DetailViewModel {
  return {
    id: "detail-1",
    type: "law",
    title: "Test Title",
    subtitle: "Test Subtitle",
    breadcrumbs: [],
    metadata,
    contentHtml,
    tabs: [],
    relatedGroups: [],
    references: [],
    annotations: [],
  };
}

describe("DetailsTab", () => {
  it("sanitizes unsafe HTML before rendering", () => {
    const maliciousHtml = `
      <p>Allowed paragraph</p>
      <img src="x" onerror="alert('xss')" />
      <script>alert('xss')</script>
    `;
    const detail = buildDetail(maliciousHtml);

    const { container } = renderWithProviders(<DetailsTab detail={detail} />);

    expect(screen.getByText("Allowed paragraph")).toBeInTheDocument();
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")?.getAttribute("onerror")).toBeNull();
  });

  it("shows a graceful empty state when no metadata and no content exist", () => {
    const detail = buildDetail("");
    renderWithProviders(<DetailsTab detail={detail} />);

    expect(screen.getByText("Keine Dokumentdetails")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Für dieses Ergebnis sind derzeit weder Metadaten noch Textinhalt verfügbar.",
      ),
    ).toBeInTheDocument();
  });

  it("renders a fallback label when metadata value is empty", () => {
    const detail = buildDetail("", [{ label: "Jurisdiction", value: "" }]);
    renderWithProviders(<DetailsTab detail={detail} />);

    expect(screen.getByText("Jurisdiction")).toBeInTheDocument();
    expect(screen.getByText("Not available")).toBeInTheDocument();
  });

  it("renders metadata icons when icon keys are present", () => {
    const detail = buildDetail("", [
      { label: "Document type", value: "Law", iconKey: "dtype-law" },
    ]);
    renderWithProviders(<DetailsTab detail={detail} />);

    expect(screen.getByText("Document type")).toBeInTheDocument();
    expect(screen.getByText("§")).toBeInTheDocument();
    expect(screen.getByText("Law")).toBeInTheDocument();
  });
});
