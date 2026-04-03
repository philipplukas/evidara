import { act, fireEvent, screen } from "@testing-library/react";
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

    const decisionsTab = screen.getByRole("button", { name: "Court decisions" });
    fireEvent.click(decisionsTab);
    expect(decisionsTab.className).toContain("text-brand");

    const officialToggle = screen.getByRole("button", { name: "Official sources only" });
    fireEvent.click(officialToggle);
    expect(officialToggle.className).toContain("text-brand");
  });

  it("writes selected detail tab to URL state", () => {
    renderWithProviders(<DetailTabs tabs={articleDetail.tabs} />, {
      searchParams: { tab: "related" },
    });

    const relatedTab = screen.getByRole("button", { name: /Related/ });
    expect(relatedTab.className).toContain("text-brand");

    fireEvent.click(screen.getByRole("button", { name: /^Details$/ }));
    expect(screen.getByRole("button", { name: /^Details$/ }).className).toContain("text-brand");
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

    fireEvent.click(screen.getByRole("button", { name: /Art\. 754 OR/ }));
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

    const backButton = screen.getByRole("button", { name: /Back/ });
    expect(backButton).toBeInTheDocument();
    expect(screen.getByText("Commentary for Art. 754 OR")).toBeInTheDocument();

    act(() => {
      fireEvent.click(backButton);
    });

    expect(screen.queryByRole("button", { name: /Back/ })).not.toBeInTheDocument();
  });
});
