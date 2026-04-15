import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DetailPanelHeader } from "@/components/detail/DetailPanelHeader";
import { DetailTabs } from "@/components/detail/DetailTabs";
import { ContextBar } from "@/components/layout/ContextBar";
import { ExactMatchStrip } from "@/components/results/ExactMatchStrip";
import { ResultSetScopeBar } from "@/components/results/ResultSetScopeBar";
import { articleDetail, searchContext, searchResults } from "@/lib/mock-data";
import { useWorkspace } from "@/lib/workspace-store";
import { renderWithProviders } from "./helpers/render-with-providers";

describe("High-impact interaction controls", () => {
  it("toggles context chips and source type tabs", () => {
    renderWithProviders(<ContextBar context={searchContext} />);

    const austriaChip = screen.getByRole("button", { name: /Austria/ });
    expect(austriaChip.className).toContain("bg-muted");
    fireEvent.click(austriaChip);
    expect(austriaChip.className).toContain("bg-brand-strong");

    const decisionsTab = screen.getByRole("button", { name: /Court decisions|Urteile/ });
    fireEvent.click(decisionsTab);
    expect(decisionsTab.className).toContain("text-brand");

    const officialToggle = screen.getByRole("button", {
      name: /Official sources only|Nur offizielle Quellen/,
    });
    fireEvent.click(officialToggle);
    expect(officialToggle.className).toContain("text-brand");
  });

  it("writes selected detail tab to URL state", async () => {
    renderWithProviders(<DetailTabs tabs={articleDetail.tabs} />, {
      searchParams: { tab: "related" },
    });

    const relatedTab = screen.getByRole("tab", { name: /Related/ });
    expect(relatedTab).toHaveAttribute("aria-selected", "true");

    // Radix TabsTrigger commits selection on mouseDown (not click).
    fireEvent.mouseDown(screen.getByRole("tab", { name: /^Details$/ }), { button: 0 });
    await waitFor(() => {
      expect(screen.getByRole("tab", { name: /^Details$/ })).toHaveAttribute(
        "aria-selected",
        "true",
      );
    });
  });

  it("fires pin and copy actions in detail header", async () => {
    const onPin = vi.fn();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    renderWithProviders(
      <DetailPanelHeader detail={articleDetail} onPin={onPin} isPinned={false} />,
    );

    const pinButton = document.querySelector('button[title="Pin"]');
    expect(pinButton).toBeTruthy();
    fireEvent.click(pinButton!);
    expect(onPin).toHaveBeenCalledWith(articleDetail.id, articleDetail.title, articleDetail.type);

    const copyButton = document.querySelector('button[title="Copy citation"]');
    expect(copyButton).toBeTruthy();
    fireEvent.click(copyButton!);
    expect(writeText).toHaveBeenCalledWith(articleDetail.title);
  });

  it("supports exact match selection", () => {
    const onSelect = vi.fn();
    renderWithProviders(<ExactMatchStrip matches={[searchResults[0]]} onSelect={onSelect} />);

    expect(screen.getByText("Exakte Treffer")).toBeInTheDocument();
    expect(screen.getByText("Hohe Übereinstimmung")).toBeInTheDocument();
    expect(screen.getByText("1 gefunden")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Exakten Treffer Art\. 754 OR öffnen/ }));
    expect(onSelect).toHaveBeenCalledWith(searchResults[0].id);
  });

  it("shows BACK action after pivot and dispatches back", () => {
    function ScopeHarness() {
      const { state, dispatch } = useWorkspace();
      return (
        <div>
          <button
            type="button"
            onClick={() =>
              dispatch({
                type: "PIVOT",
                source: {
                  type: "pivot",
                  label: "Commentary",
                  parentSource: state.resultSet.source,
                },
                results: [searchResults[1]],
                scopeLabel: "Commentary for Art. 754 OR",
              })
            }
          >
            pivot-now
          </button>
          <ResultSetScopeBar />
        </div>
      );
    }

    renderWithProviders(<ScopeHarness />);
    fireEvent.click(screen.getByRole("button", { name: "pivot-now" }));

    const backButton = screen.getByRole("button", { name: /Zum vorherigen Bereich/ });
    expect(backButton).toBeInTheDocument();
    expect(screen.getByText("Aktueller Bereich")).toBeInTheDocument();
    expect(screen.getByText("Eingegrenzter Bereich")).toBeInTheDocument();
    expect(screen.getByText("Commentary for Art. 754 OR")).toBeInTheDocument();
    expect(screen.getByText(/Search for "Art 754 OR" · Commentary/)).toBeInTheDocument();
    expect(screen.getByText("Vorheriger Bereich")).toBeInTheDocument();
    expect(screen.getByText(/Results for "Art 754 OR" erneut öffnen/)).toBeInTheDocument();
    expect(
      screen.getByText(
        /Der Bereich wurde gegenüber der vorherigen Ergebnismenge eingegrenzt, damit die aktuellen Belege fokussierter bleiben\./,
      ),
    ).toBeInTheDocument();

    act(() => {
      fireEvent.click(backButton);
    });

    expect(screen.queryByRole("button", { name: /Back/ })).not.toBeInTheDocument();
  });
});
