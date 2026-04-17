import { fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactElement } from "react";
import { describe, expect, it } from "vitest";
import { MetadataList } from "@/components/detail/MetadataList";
import { MESSAGES } from "@/i18n/messages";
import type { MetadataField } from "@/lib/types";

function fieldsFixture(): MetadataField[] {
  return [
    { label: "Court", value: "Supreme", visibility: "always" },
    { label: "Docket", value: "1", visibility: "default" },
    { label: "Internal", value: "hidden until expanded", visibility: "expanded" },
  ];
}

function renderMetadataList(ui: ReactElement) {
  return render(
    <NextIntlClientProvider locale="de" messages={MESSAGES.de}>
      {ui}
    </NextIntlClientProvider>,
  );
}

describe("MetadataList", () => {
  it("shows empty state when there are no fields", () => {
    renderMetadataList(<MetadataList fields={[]} />);
    expect(screen.getByText("Keine Metadaten verfügbar")).toBeInTheDocument();
  });

  it("compact density shows only always-visible rows", () => {
    renderMetadataList(<MetadataList fields={fieldsFixture()} initialDensity="compact" />);
    expect(screen.getByText("Court")).toBeInTheDocument();
    expect(screen.queryByText("Docket")).not.toBeInTheDocument();
    expect(screen.queryByText("Internal")).not.toBeInTheDocument();
  });

  it("default density shows always and default rows", () => {
    renderMetadataList(<MetadataList fields={fieldsFixture()} initialDensity="default" />);
    expect(screen.getByText("Court")).toBeInTheDocument();
    expect(screen.getByText("Docket")).toBeInTheDocument();
    expect(screen.queryByText("Internal")).not.toBeInTheDocument();
  });

  it("expanded density shows all rows", () => {
    renderMetadataList(<MetadataList fields={fieldsFixture()} initialDensity="expanded" />);
    expect(screen.getByText("Court")).toBeInTheDocument();
    expect(screen.getByText("Docket")).toBeInTheDocument();
    expect(screen.getByText("Internal")).toBeInTheDocument();
  });

  it("expands from default to show hidden fields", () => {
    renderMetadataList(<MetadataList fields={fieldsFixture()} initialDensity="default" />);
    expect(screen.queryByText("Internal")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /1 weitere Felder anzeigen/ }));
    expect(screen.getByText("Internal")).toBeInTheDocument();
  });

  it("expands from compact to show all fields (header context)", () => {
    renderMetadataList(
      <MetadataList fields={fieldsFixture()} initialDensity="compact" showHeading={false} />,
    );
    expect(screen.getByText("Court")).toBeInTheDocument();
    expect(screen.queryByText("Docket")).not.toBeInTheDocument();
    expect(screen.queryByText("Internal")).not.toBeInTheDocument();
    expect(screen.queryByText("Metadaten")).not.toBeInTheDocument();

    const toggle = screen.getByRole("button", { name: /weitere Felder anzeigen/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);

    expect(screen.getByText("Docket")).toBeInTheDocument();
    expect(screen.getByText("Internal")).toBeInTheDocument();
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });

  it("collapses back to initial density after expanding", () => {
    renderMetadataList(<MetadataList fields={fieldsFixture()} initialDensity="default" />);

    fireEvent.click(screen.getByRole("button", { name: /1 weitere Felder anzeigen/ }));
    expect(screen.getByText("Internal")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /weniger/i }));
    expect(screen.queryByText("Internal")).not.toBeInTheDocument();
    expect(screen.getByText("Docket")).toBeInTheDocument();
  });

  it("toggle button has aria-expanded reflecting current state", () => {
    renderMetadataList(<MetadataList fields={fieldsFixture()} initialDensity="default" />);
    const toggle = screen.getByRole("button", { name: /weitere Felder anzeigen/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(toggle);
    const collapseBtn = screen.getByRole("button", { name: /weniger/i });
    expect(collapseBtn).toHaveAttribute("aria-expanded", "true");
  });
});
