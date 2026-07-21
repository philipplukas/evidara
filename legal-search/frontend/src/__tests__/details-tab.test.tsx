import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DetailsTab } from "@/components/detail/tabs/DetailsTab";
import type { DetailViewModel } from "@/lib/types";
import { renderWithProviders } from "./helpers/render-with-providers";

function buildDetail(
  contentText: string,
  metadata: DetailViewModel["metadata"] = [],
): DetailViewModel {
  return {
    id: "detail-1",
    type: "law",
    title: "Test Title",
    subtitle: "Test Subtitle",
    breadcrumbs: [],
    metadata,
    contentText,
    tabs: [],
    relatedGroups: [],
    references: [],
    annotations: [],
  };
}

describe("DetailsTab", () => {
  it("renders the document body text", () => {
    const detail = buildDetail("Erste Erwägung.\n\nZweite Erwägung.");

    renderWithProviders(<DetailsTab detail={detail} />);

    expect(screen.getByText("Erste Erwägung.")).toBeInTheDocument();
    expect(screen.getByText("Zweite Erwägung.")).toBeInTheDocument();
  });

  // The body is plain text, so markup in it is content, not instructions. React
  // escapes it; there is no sanitizer to get wrong and no `innerHTML` to abuse.
  it("renders markup-looking body text literally, never as markup", () => {
    const detail = buildDetail(`<img src="x" onerror="alert('xss')"><script>alert('xss')</script>`);

    const { container } = renderWithProviders(<DetailsTab detail={detail} />);

    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(
      screen.getByText(`<img src="x" onerror="alert('xss')"><script>alert('xss')</script>`),
    ).toBeInTheDocument();
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
    const detail = buildDetail("", [{ label: "Jurisdiction", value: "", visibility: "always" }]);
    renderWithProviders(<DetailsTab detail={detail} />);

    expect(screen.getByText("Jurisdiction")).toBeInTheDocument();
    expect(screen.getByText("Nicht verfügbar")).toBeInTheDocument();
  });

  it("renders metadata icons when icon keys are present", () => {
    const detail = buildDetail("", [
      { label: "Document type", value: "Law", iconKey: "dtype-law", visibility: "always" },
    ]);
    const { container } = renderWithProviders(<DetailsTab detail={detail} />);

    expect(screen.getByText("Document type")).toBeInTheDocument();
    // Was `getByText("§")`. Document-meta icons are lucide components now, not
    // text glyphs, so the icon is an <svg> rather than a text node (issue 694).
    expect(container.querySelector("svg.lucide-scroll")).toBeInTheDocument();
    expect(screen.getByText("Law")).toBeInTheDocument();
  });

  it("hides expanded-only metadata until the expand control is used", () => {
    const detail = buildDetail("", [
      { label: "Jurisdiction", value: "CH", visibility: "always" },
      // `expanded` now comes from the BFF. This case used to rely on the client
      // heuristic resolving an unrecognized English label to "expanded" — a rule
      // that could never fire against the BFF's real German labels (#787).
      { label: "Custom field", value: "Extra", visibility: "expanded" },
    ]);
    renderWithProviders(<DetailsTab detail={detail} />);

    expect(screen.getByText("Jurisdiction")).toBeInTheDocument();
    expect(screen.queryByText("Custom field")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /1 weiteres Feld anzeigen/ })).toBeInTheDocument();
  });
});
