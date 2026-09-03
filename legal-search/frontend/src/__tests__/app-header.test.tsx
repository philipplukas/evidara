import { fireEvent, screen, waitFor } from "@testing-library/react";
import type { UrlUpdateEvent } from "nuqs/adapters/testing";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppHeader } from "@/components/layout/AppHeader";
import { searchResults } from "@/lib/mock-data";
import { DEFAULT_SEARCH_QUERY } from "@/lib/search-params";
import { useWorkspace } from "@/lib/workspace-store";
import { renderWithProviders } from "./helpers/render-with-providers";

/**
 * Renders the header beside a button that pivots the workspace, so a test can
 * observe the header inside a result set that is not a search.
 */
function PivotHarness(props: Parameters<typeof AppHeader>[0]) {
  const { state, dispatch } = useWorkspace();
  return (
    <div>
      <button
        type="button"
        onClick={() =>
          dispatch({
            type: "PIVOT",
            source: { type: "pivot", label: "Commentary", parentSource: state.resultSet.source },
            results: [searchResults[1]],
            scopeLabel: "Commentary for Art. 754 OR",
          })
        }
      >
        pivot-now
      </button>
      <AppHeader {...props} />
    </div>
  );
}

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

  // `q` has one parser and one default (`searchParamsParsers.q`), so `urlQuery`
  // is never the empty string the two reads below used to lean on (#822).
  it("hands the control plane the store's query, not the URL's", () => {
    renderWithProviders(
      <AppHeader controlPanelUrl="https://ops.example/admin" showControlPlaneEntry={true} />,
      { searchParams: { q: "Stale URL query" }, initialQuery: "Art 754 OR" },
    );

    const href = screen.getByRole("link", { name: /Kontrollbereich/ }).getAttribute("href");
    const url = new URL(href!);
    // `ls_scope` is derived from the store, so `ls_query` must be too — the two
    // halves of one handoff cannot describe different result sets.
    expect(url.searchParams.get("ls_query")).toBe("Art 754 OR");
    expect(url.searchParams.get("ls_scope")).toBe("Ergebnisse für „Art 754 OR“");
  });

  it("sends no query and runs no search while the result set is a pivot", () => {
    const onSearch = vi.fn().mockResolvedValue(undefined);

    renderWithProviders(
      <PivotHarness
        onSearch={onSearch}
        controlPanelUrl="https://ops.example/admin"
        showControlPlaneEntry={true}
      />,
      { searchParams: { q: "Art 754 OR" }, initialQuery: "Art 754 OR" },
    );

    onSearch.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "pivot-now" }));

    // A pivot has no search query; `?q=` still holds the one it was reached
    // from. Sending it would contradict `ls_scope`, and re-running it would
    // throw the user straight back out of the pivot.
    const href = screen.getByRole("link", { name: /Kontrollbereich/ }).getAttribute("href");
    expect(new URL(href!).searchParams.get("ls_query")).toBeNull();
    expect(onSearch).not.toHaveBeenCalled();
  });

  it("keeps a searched query in the URL when it happens to equal the default", async () => {
    // nuqs deletes a param whose written value equals the parser default
    // (`clearOnDefault`, on by default). Giving `q` an honest default armed
    // that: without `clearOnDefault: false` the user searches
    // `DEFAULT_SEARCH_QUERY`, watches it vanish from the address bar, and the
    // link they copy resolves to whatever that constant is when it is opened
    // rather than to the query they ran (#822).
    const updates: UrlUpdateEvent[] = [];
    const onSearch = vi.fn().mockResolvedValue(undefined);

    renderWithProviders(
      <AppHeader onSearch={onSearch} controlPanelUrl={undefined} showControlPlaneEntry={true} />,
      {
        searchParams: { q: "foo" },
        initialQuery: "foo",
        onUrlUpdate: (event) => updates.push(event),
      },
    );

    const input = screen.getByPlaceholderText("Nach Artikel, Urteil, Kommentar oder Zitat suchen…");
    fireEvent.change(input, { target: { value: DEFAULT_SEARCH_QUERY } });
    fireEvent.click(screen.getByRole("button", { name: "Suchen" }));

    await waitFor(() => expect(updates.length).toBeGreaterThan(0));
    expect(updates.at(-1)?.searchParams.get("q")).toBe(DEFAULT_SEARCH_QUERY);
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
