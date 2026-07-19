import { fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppHeader } from "@/components/layout/AppHeader";
import { renderWithProviders } from "./helpers/render-with-providers";

describe("AppHeader", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("centers the search field and exposes the control-plane handoff when configured", () => {
    renderWithProviders(
      <AppHeader controlPanelUrl="https://ops.example/admin" showControlPlaneEntry={true} />,
    );

    expect(
      screen.getByPlaceholderText("Nach Artikel, Urteil, Kommentar oder Zitat suchen…"),
    ).toBeInTheDocument();
    const controlPlaneLink = screen.getByRole("link", { name: /Kontrollbereich/ });
    const href = controlPlaneLink.getAttribute("href");
    expect(href).toBeTruthy();
    const url = new URL(href!);
    expect(`${url.origin}${url.pathname}`).toBe("https://ops.example/admin");
    expect(url.searchParams.get("from")).toBe("legal-search");
    expect(url.searchParams.get("ls_query")).toBe("Art 754 OR");
    // Localized: the scope label handed to the control plane is human-readable
    // context, and it is derived through the same translator the workspace
    // renders (#648 — it used to be a hardcoded English `Results for "…"`).
    expect(url.searchParams.get("ls_scope")).toBe("Ergebnisse für „Art 754 OR“");
    expect(controlPlaneLink).not.toHaveAttribute("target");
    expect(controlPlaneLink).not.toHaveAttribute("rel");
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

  it("surfaces recent searches and reuses them as quick actions", async () => {
    window.localStorage.setItem(
      "evidara.recent-queries",
      JSON.stringify(["Art. 754 OR", "Verantwortlichkeit"]),
    );
    const onSearch = vi.fn().mockResolvedValue(undefined);

    renderWithProviders(
      <AppHeader onSearch={onSearch} controlPanelUrl={undefined} showControlPlaneEntry={true} />,
      { initialQuery: "" },
    );

    const recentSearch = screen.getByRole("button", { name: "Art. 754 OR" });
    fireEvent.click(recentSearch);

    expect(onSearch).toHaveBeenCalledWith("Art. 754 OR");
  });

  it("disables the submit action until the input has content and shows loading feedback", async () => {
    const onSearch = vi.fn(
      () =>
        new Promise<void>(() => {
          // Keep the request pending so the loading state remains visible.
        }),
    );

    renderWithProviders(
      <AppHeader onSearch={onSearch} controlPanelUrl={undefined} showControlPlaneEntry={true} />,
      { initialQuery: "" },
    );

    const input = screen.getByPlaceholderText("Nach Artikel, Urteil, Kommentar oder Zitat suchen…");
    const submit = screen.getByRole("button", { name: "Suchen" });

    expect(submit).toBeDisabled();

    fireEvent.change(input, { target: { value: "Art. 754 OR" } });
    expect(submit).toBeEnabled();

    fireEvent.click(submit);

    expect(submit).toBeDisabled();
    expect(screen.getByRole("button", { name: "Suche läuft" })).toBeInTheDocument();
  });

  it("focuses the search field from a global slash shortcut", () => {
    renderWithProviders(<AppHeader controlPanelUrl={undefined} showControlPlaneEntry={true} />);

    const input = screen.getByPlaceholderText("Nach Artikel, Urteil, Kommentar oder Zitat suchen…");

    fireEvent.keyDown(window, { key: "/" });

    expect(input).toHaveFocus();
  });

  it("does not steal slash key presses from text-entry targets", () => {
    renderWithProviders(<AppHeader controlPanelUrl={undefined} showControlPlaneEntry={true} />);

    const input = screen.getByPlaceholderText("Nach Artikel, Urteil, Kommentar oder Zitat suchen…");
    const textarea = document.createElement("textarea");
    document.body.append(textarea);
    textarea.focus();

    fireEvent.keyDown(textarea, { key: "/" });

    expect(textarea).toHaveFocus();
    expect(input).not.toHaveFocus();

    textarea.remove();
  });
});
