import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AnnotationTab } from "@/components/detail/tabs/AnnotationTab";
import { DetailsTab } from "@/components/detail/tabs/DetailsTab";
import { ReferencesTab } from "@/components/detail/tabs/ReferencesTab";
import { RelatedTab } from "@/components/detail/tabs/RelatedTab";
import { StructureTab } from "@/components/detail/tabs/StructureTab";
import type { DetailViewModel } from "@/lib/types";
import { renderWithProviders } from "./helpers/render-with-providers";

function buildDetail(overrides: Partial<DetailViewModel> = {}): DetailViewModel {
  return {
    id: "detail-1",
    type: "law",
    title: "Test Title",
    subtitle: "Test Subtitle",
    breadcrumbs: [],
    metadata: [],
    contentHtml: "",
    tabs: [],
    relatedGroups: [],
    references: [],
    annotations: [],
    ...overrides,
  };
}

describe("Detail tab empty states", () => {
  it("shows a friendly empty state for annotations", () => {
    renderWithProviders(<AnnotationTab annotations={[]} />);

    expect(screen.getByText("Keine Anmerkungen verfügbar")).toBeInTheDocument();
  });

  it("shows a friendly empty state for related materials", () => {
    renderWithProviders(<RelatedTab groups={[]} sourceId="detail-1" />);

    expect(screen.getByText("Keine verknüpften Materialien")).toBeInTheDocument();
  });

  it("shows a friendly empty state for references", () => {
    renderWithProviders(
      <ReferencesTab references={[]} sourceId="detail-1" sourceTitle="Test Title" />,
    );

    expect(screen.getByText("Keine Verweise")).toBeInTheDocument();
  });

  it("shows a friendly empty state for local structure", () => {
    renderWithProviders(<StructureTab items={[]} />);

    expect(screen.getByText("Keine lokale Struktur")).toBeInTheDocument();
  });

  it("keeps the details fallback readable when metadata and content are missing", () => {
    renderWithProviders(<DetailsTab detail={buildDetail()} />);

    expect(screen.getByText("Keine Dokumentdetails")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Für dieses Ergebnis sind derzeit weder Metadaten noch Textinhalt verfügbar.",
      ),
    ).toBeInTheDocument();
  });
});
