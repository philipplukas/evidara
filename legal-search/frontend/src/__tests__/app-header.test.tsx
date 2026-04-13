import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AppHeader } from "@/components/layout/AppHeader";
import { renderWithProviders } from "./helpers/render-with-providers";

describe("AppHeader", () => {
  it("centers the search field and exposes the control-plane handoff when configured", () => {
    const { container } = renderWithProviders(
      <AppHeader controlPanelUrl="https://ops.example/admin" showControlPlaneEntry={true} />,
    );

    expect(
      screen.getByPlaceholderText("Nach Artikel, Urteil, Kommentar oder Zitat suchen…"),
    ).toBeInTheDocument();
    const controlPlaneLink = screen.getByRole("link", { name: /OperatorKontrollbereich/ });
    const href = controlPlaneLink.getAttribute("href");
    expect(href).toBeTruthy();
    const url = new URL(href!);
    expect(`${url.origin}${url.pathname}`).toBe("https://ops.example/admin");
    expect(url.searchParams.get("from")).toBe("legal-search");
    expect(url.searchParams.get("ls_query")).toBe("Art 754 OR");
    expect(url.searchParams.get("ls_scope")).toBe('Results for "Art 754 OR"');
    expect(container.querySelector(".app-header__control-plane-kicker")).toHaveTextContent(
      "Operator",
    );
  });

  it("keeps the control-plane entry visibly disabled when no URL is available", () => {
    renderWithProviders(<AppHeader controlPanelUrl={undefined} showControlPlaneEntry={true} />);

    const button = screen.getByRole("button", { name: "Kontrollbereich" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute(
      "title",
      "Kontrollbereich-URL ist für diese Umgebung nicht konfiguriert.",
    );
  });
});
