/**
 * Reading mode: the reader in the centre, the outline beside it, the evidence
 * beside that (#1053).
 *
 * WHY THESE TESTS EXIST
 *
 * The complaint #1053 measures is not "the panel is narrow", it is that the
 * outline lived behind a tab that REPLACED the text: for the ZGB's 1,377
 * sections, seeing where you are and reading where you are were two different
 * screens. So the load-bearing assertion here is that the outline and the body
 * are on screen at the same time, and that choosing a section moves the reader
 * rather than navigating.
 *
 * What jsdom cannot see, and is therefore asserted elsewhere: rendered widths,
 * the collapse order and the characters-per-line measure. Those are
 * `reading-layout.test.ts` (the rule) and `e2e/workspace-panels.spec.ts` (the
 * rendered geometry, in a real browser).
 */
import { fireEvent, screen, within } from "@testing-library/react";
import type { OnUrlUpdateFunction } from "nuqs/adapters/testing";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import WorkspaceClient from "@/app/WorkspaceClient";
import { filters, searchContext, searchResults } from "@/lib/mock-data";
import type { DetailViewModel } from "@/lib/types";
import { renderWithProviders } from "./helpers/render-with-providers";

const BODY = [
  "I. Allgemeine Bestimmungen",
  "Dieses Gesetz regelt die Haltung von Hunden im Kanton Zuerich.",
  "§ 1 Meldepflicht",
  "Wer einen Hund haelt, meldet ihn innert zehn Tagen der Wohnsitzgemeinde.",
  "§ 2 Leinenpflicht",
  "Der Gemeinderat kann fuer bestimmte Gebiete eine Leinenpflicht anordnen.",
].join("\n\n");

const hundegesetz: DetailViewModel = {
  id: "doc_zh_hundegesetz",
  type: "law",
  title: "Hundegesetz",
  subtitle: "Kanton Zürich",
  breadcrumbs: ["Kanton ZH", "Ordnungsrecht"],
  metadata: [],
  contentText: BODY,
  tabs: [
    { key: "content", label: "Inhalt" },
    { key: "sections", label: "Abschnitte", count: 3 },
    { key: "citations", label: "Verweise", count: 2 },
    { key: "details", label: "Details" },
  ],
  relatedGroups: [],
  references: [
    {
      direction: "SR",
      items: [
        {
          id: "cit_ok",
          title: "Tierschutzgesetz",
          citation: "SR 455.1",
          resolved: true,
          targetDocumentId: "doc_tschg",
          href: "/documents/doc_tschg",
        },
        {
          id: "cit_missing",
          title: "SR 210",
          citation: "SR 210",
          resolved: false,
          unresolvedReason: "no_target_in_corpus",
        },
      ],
    },
  ],
  annotations: [],
  localStructure: {
    items: [
      {
        id: "sec_1",
        label: "I. Allgemeine Bestimmungen",
        active: false,
        depth: 0,
        text: "Dieses Gesetz regelt die Haltung von Hunden im Kanton Zuerich.",
      },
      {
        id: "sec_2",
        label: "§ 1 Meldepflicht",
        active: false,
        depth: 1,
        text: "Wer einen Hund haelt, meldet ihn innert zehn Tagen der Wohnsitzgemeinde.",
      },
      {
        id: "sec_3",
        label: "§ 2 Leinenpflicht",
        active: false,
        depth: 1,
        text: "Der Gemeinderat kann fuer bestimmte Gebiete eine Leinenpflicht anordnen.",
      },
    ],
  },
};

vi.mock("@/hooks/use-desktop", () => ({ useDesktop: () => true }));

/**
 * The document the mocked fetch returns, swappable per test.
 *
 * Hoisted rather than captured, because `vi.mock` factories run before the
 * module body. A test that builds a second fixture and forgets to install it
 * asserts against the first one and passes unconditionally — which is exactly
 * what the "no jump for an unplaced section" case would have done.
 */
const detailState = vi.hoisted(() => ({ current: null as unknown }));

vi.mock("@/hooks/use-detail", () => ({
  useDetail: () => ({
    data: detailState.current,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
}));

// jsdom has no layout, so the real panels would measure nothing. Everything
// about WIDTH is asserted in `reading-layout.test.ts` and in Playwright; this
// double only has to keep the children in the tree.
vi.mock("@/components/ui/resizable-panels", () => ({
  ResizablePanelGroup: ({ children }: { children: ReactNode }) => (
    <div data-testid="panel-group">{children}</div>
  ),
  ResizablePanel: ({ children }: { children: ReactNode }) => (
    <section data-testid="panel">{children}</section>
  ),
  ResizableHandle: () => <div data-testid="panel-handle" />,
}));

vi.mock("@/components/layout/AppHeader", () => ({ AppHeader: () => <div>app-header</div> }));
vi.mock("@/components/layout/ContextBar", () => ({ ContextBar: () => <div>context-bar</div> }));
vi.mock("@/components/filters/FilterPanel", () => ({
  FilterPanel: ({ collapsed }: { collapsed?: boolean }) => (
    <div>filter-panel-collapsed-{String(Boolean(collapsed))}</div>
  ),
}));
vi.mock("@/components/results/ResultContextHeader", () => ({
  ResultContextHeader: () => <div>result-context-header</div>,
}));
vi.mock("@/components/results/ResultList", () => ({
  ResultList: () => <div>result-strip</div>,
}));

/** Elements `scrollIntoView` was called on. jsdom implements no layout. */
let scrolledTo: HTMLElement[] = [];

beforeEach(() => {
  detailState.current = hundegesetz;
  scrolledTo = [];
  Element.prototype.scrollIntoView = function scrollIntoView(this: HTMLElement) {
    scrolledTo.push(this);
  };
});

function renderReadingMode(onUrlUpdate?: OnUrlUpdateFunction) {
  return renderWithProviders(<WorkspaceClient searchContext={searchContext} filters={filters} />, {
    initialResults: searchResults,
    searchParams: { item: hundegesetz.id },
    onUrlUpdate,
  });
}

describe("reading mode", () => {
  it("shows the outline and the document text at the same time", () => {
    // The whole of #1053's premise. Before it, "Abschnitte" replaced the body:
    // the outline and the text could not both be on screen.
    renderReadingMode();

    const outline = screen.getByRole("navigation", { name: "Gliederung" });
    expect(within(outline).getByRole("button", { name: /Meldepflicht/ })).toBeInTheDocument();
    expect(
      screen.getByText("Wer einen Hund haelt, meldet ihn innert zehn Tagen der Wohnsitzgemeinde."),
    ).toBeInTheDocument();
  });

  it("opens in the text rather than on the metadata list", () => {
    renderReadingMode();

    expect(screen.getByTestId("reader-body")).toBeInTheDocument();
    expect(
      screen.queryByText("Metadaten stehen zuerst,", { exact: false }),
    ).not.toBeInTheDocument();
  });

  it("drops the tabs the rails now own", () => {
    // Leaving "Abschnitte" and "Verweise" in the strip would put each of them
    // on screen twice, and the tab has no scroll spy — the two would disagree
    // about which section you are in.
    renderReadingMode();

    expect(screen.queryByRole("tab", { name: /Abschnitte/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /Verweise/ })).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Inhalt/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^Details$/ })).toBeInTheDocument();
  });

  it("moves the reader when a section is chosen, and selects no document", () => {
    // Defect 3 of #1040, at the new layout: the rail hands out `section_id`s
    // and feeding one to the workspace's document selection is what made
    // every outline click a `GET /v1/documents/sec_…` 404.
    const urlUpdates: string[] = [];
    renderReadingMode((update) => urlUpdates.push(update.queryString));

    const outline = screen.getByRole("navigation", { name: "Gliederung" });
    fireEvent.click(within(outline).getByRole("button", { name: /Leinenpflicht/ }));

    // The reader moved: the heading exists whether or not anything was
    // clicked, so what is asserted is the scroll, to that section's anchor.
    expect(scrolledTo.map((element) => element.dataset.sectionId)).toEqual(["sec_3"]);
    // And no document was selected. `sec_…` reaching `item` is the #1040 404.
    for (const queryString of urlUpdates) {
      expect(queryString).toContain(`item=${hundegesetz.id}`);
      expect(queryString).not.toContain("item=sec_");
    }
  });

  it("offers no jump for a section the body does not carry", () => {
    // GUARD. A row with nowhere to scroll to must not be a control: accepting
    // the click and scrolling nowhere is indistinguishable from a jump that
    // worked.
    const unplaced: DetailViewModel = {
      ...hundegesetz,
      localStructure: {
        items: [
          ...(hundegesetz.localStructure?.items ?? []),
          { id: "sec_9", label: "§ 9 Nicht im Text", active: false, depth: 1 },
        ],
      },
    };
    detailState.current = unplaced;
    renderReadingMode();

    const outline = screen.getByRole("navigation", { name: "Gliederung" });
    // Present and readable — it has a label — but not a control.
    expect(within(outline).getByText("§ 9 Nicht im Text")).toBeInTheDocument();
    expect(
      within(outline).queryByRole("button", { name: /Nicht im Text/ }),
    ).not.toBeInTheDocument();
    expect(within(outline).getByRole("button", { name: /Meldepflicht/ })).toBeInTheDocument();
  });
});

describe("reading mode evidence rail", () => {
  it("renders the outgoing references beside the text", () => {
    renderReadingMode();

    const rail = screen.getByRole("complementary", { name: "Belege" });
    expect(within(rail).getByText("SR 455.1")).toBeInTheDocument();
    expect(within(rail).getByRole("button", { name: /Tierschutzgesetz/ })).toBeInTheDocument();
  });

  it("does not render an unresolvable citation as a working link", () => {
    // GUARD (ADR-0052 — unknown is not zero). Every citation on the ZH
    // Hundegesetz carries `no_target_in_corpus`.
    renderReadingMode();

    const rail = screen.getByRole("complementary", { name: "Belege" });
    expect(within(rail).queryByRole("button", { name: /SR 210/ })).not.toBeInTheDocument();
    const unresolved = rail.querySelector('[data-unresolved="true"]') as HTMLElement;
    expect(unresolved).not.toBeNull();
    expect(
      within(unresolved).getByText("Die zitierte Norm ist nicht im Bestand."),
    ).toBeInTheDocument();
  });

  it("states where the document sits", () => {
    renderReadingMode();

    const rail = screen.getByRole("complementary", { name: "Belege" });
    expect(within(rail).getByText("Einordnung")).toBeInTheDocument();
    expect(within(rail).getByText("Kanton ZH")).toBeInTheDocument();
  });

  it("carries no incoming-references section at all", () => {
    // GUARD. `zitiert von` needs the reverse-citation endpoints, which exist
    // with zero call sites (#912). A rendered "Zitiert von (0)" would read as
    // "no norm cites this one" — a claim the corpus cannot make. Absent, not
    // empty. Add such a section and this list stops matching.
    renderReadingMode();

    const rail = screen.getByRole("complementary", { name: "Belege" });
    const headings = Array.from(rail.querySelectorAll("p")).map((p) => p.textContent?.trim());
    expect(headings).toEqual(["Belege", "Einordnung", "Verweise", "SR2"]);
  });
});
