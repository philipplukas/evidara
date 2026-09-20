/**
 * The document reader's structure, and the links that used to 404.
 *
 * WHY THESE TESTS EXIST:
 * Four defects were measured live against production on 2026-09-19 (#1040),
 * and each one had a test-shaped hole under it:
 *
 *   1. Section text was dropped by the BFF mapper.
 *   2. Section depth was dropped again by `mapDetail`, so 1,377 ZGB sections
 *      rendered at one indent.
 *   3. Clicking a section passed a `section_id` to the *document* endpoint —
 *      `GET /v1/documents/sec_…` → 404 → "Dieses Dokument ist nicht mehr
 *      verfügbar."
 *   4. Clicking a citation did the same with a `citation_id`, while the BFF's
 *      `href` went unread.
 *
 * The suite that shipped all four was green: `keyboard-interactions.test.tsx`
 * asserted `onFocus("art-755")` — the 404 — as correct behaviour.
 */

import { fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DetailPanel } from "@/components/detail/DetailPanel";
import { ReferencesTab } from "@/components/detail/tabs/ReferencesTab";
import { StructureTab } from "@/components/detail/tabs/StructureTab";
import type { DetailViewModel, ReferenceItem } from "@/lib/types";
import { renderWithProviders } from "./helpers/render-with-providers";

const BODY = [
  "I. Allgemeine Bestimmungen",
  "Dieses Gesetz regelt die Haltung von Hunden im Kanton Zuerich.",
  "§ 1 Meldepflicht",
  "Wer einen Hund haelt, meldet ihn innert zehn Tagen der Wohnsitzgemeinde.",
].join("\n\n");

const hundegesetz: DetailViewModel = {
  id: "doc_zh_hundegesetz",
  type: "law",
  title: "Hundegesetz",
  subtitle: "Kanton Zürich",
  breadcrumbs: [],
  metadata: [],
  contentText: BODY,
  tabs: [
    { key: "content", label: "Inhalt" },
    { key: "sections", label: "Abschnitte", count: 2 },
    { key: "details", label: "Details" },
  ],
  relatedGroups: [],
  references: [],
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
    ],
  },
};

const reference = (over: Partial<ReferenceItem> & { id: string }): ReferenceItem => ({
  title: over.id,
  citation: over.id,
  resolved: false,
  ...over,
});

describe("StructureTab", () => {
  it("renders each section's text, not just its label", () => {
    renderWithProviders(<StructureTab items={hundegesetz.localStructure!.items} />);

    expect(
      screen.getByText("Wer einen Hund haelt, meldet ihn innert zehn Tagen der Wohnsitzgemeinde."),
    ).toBeInTheDocument();
  });

  it("indents a nested section deeper than its parent", () => {
    // Every entry rendered at one indent while `depth` was being dropped, so
    // a 1,377-section statute read as a flat list.
    renderWithProviders(
      <StructureTab
        items={hundegesetz.localStructure!.items}
        onSelectSection={vi.fn()}
        anchoredIds={new Set(["sec_1", "sec_2"])}
      />,
    );

    const parent = screen.getByRole("button", { name: /Allgemeine Bestimmungen/ });
    const child = screen.getByRole("button", { name: /Meldepflicht/ });

    expect(parent.className).toContain("ps-0");
    expect(child.className).toContain("ps-4");
  });

  it("does not offer a click for a section that is not in the body", () => {
    // GUARD. Drop the `canJump` check and this goes red: the row becomes a
    // button that accepts a click and scrolls nowhere, which looks exactly
    // like a jump that worked.
    renderWithProviders(
      <StructureTab
        items={hundegesetz.localStructure!.items}
        onSelectSection={vi.fn()}
        anchoredIds={new Set(["sec_1"])}
      />,
    );

    expect(screen.getByRole("button", { name: /Allgemeine Bestimmungen/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Meldepflicht/ })).not.toBeInTheDocument();
    // Still readable — it has a label and its text, it just has no anchor.
    expect(screen.getByText("§ 1 Meldepflicht")).toBeInTheDocument();
  });
});

describe("DetailPanel — a section click moves the reader", () => {
  it("renders section headings with anchors in the body", () => {
    const { container } = renderWithProviders(
      <DetailPanel detail={hundegesetz} onFocus={vi.fn()} />,
      { searchParams: { item: hundegesetz.id, tab: "content" } },
    );

    const headings = container.querySelectorAll("[data-section-id]");
    expect(Array.from(headings).map((h) => h.getAttribute("id"))).toEqual([
      "section-sec_1",
      "section-sec_2",
    ]);
  });

  it("switches to the body instead of navigating to the section id", () => {
    // The whole of defect 3. `onFocus` is the workspace's *document*
    // selection; handing it `sec_…` is what produced the 404.
    const onFocus = vi.fn();
    renderWithProviders(<DetailPanel detail={hundegesetz} onFocus={onFocus} />, {
      searchParams: { item: hundegesetz.id, tab: "sections" },
    });

    fireEvent.click(screen.getByRole("button", { name: /Meldepflicht/ }));

    expect(onFocus).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: "§ 1 Meldepflicht" })).toBeInTheDocument();
  });

  it("offers no section jump when the document carries no body", () => {
    const bodyless = { ...hundegesetz, contentText: undefined };
    const onFocus = vi.fn();
    renderWithProviders(<DetailPanel detail={bodyless} onFocus={onFocus} />, {
      searchParams: { item: bodyless.id, tab: "sections" },
    });

    expect(screen.queryByRole("button", { name: /Meldepflicht/ })).not.toBeInTheDocument();
    expect(onFocus).not.toHaveBeenCalled();
  });
});

describe("ReferencesTab", () => {
  const groups = [
    {
      direction: "SR",
      items: [
        reference({
          id: "cit_ok",
          title: "Tierschutzgesetz",
          citation: "SR 455.1",
          resolved: true,
          targetDocumentId: "doc_tschg",
          href: "/documents/doc_tschg",
        }),
        reference({
          id: "cit_missing",
          title: "SR 210",
          citation: "SR 210",
          resolved: false,
          unresolvedReason: "no_target_in_corpus",
        }),
      ],
    },
  ];

  it("renders the citation text the API sends", () => {
    // `ReferencesTab` rendered `item.subtitle` — a key no response carries —
    // so every row showed its title alone and four distinct citations on the
    // ZH Hundegesetz read as two repeated labels.
    renderWithProviders(
      <ReferencesTab references={groups} sourceId="doc_1" sourceTitle="Hundegesetz" />,
    );

    expect(screen.getByText("SR 455.1")).toBeInTheDocument();
  });

  it("follows the resolved citation to its target document", () => {
    const onFocus = vi.fn();
    renderWithProviders(
      <ReferencesTab
        references={groups}
        onFocus={onFocus}
        sourceId="doc_1"
        sourceTitle="Hundegesetz"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Tierschutzgesetz/ }));

    // The document id, never the citation id — `cit_…` is what 404'd.
    expect(onFocus).toHaveBeenCalledWith("doc_tschg");
    expect(onFocus).not.toHaveBeenCalledWith("cit_ok");
  });

  it("does not render an unresolved citation as a working link", () => {
    // GUARD (ADR-0052 — unknown is not zero). Remove the `!item.resolved ||
    // !item.targetDocumentId` branch in `ReferencesTab` and both assertions
    // below go red: the row becomes an `InteractiveRow` whose click sends the
    // reader to a norm the corpus does not hold.
    const onFocus = vi.fn();
    const { container } = renderWithProviders(
      <ReferencesTab
        references={groups}
        onFocus={onFocus}
        sourceId="doc_1"
        sourceTitle="Hundegesetz"
      />,
    );

    expect(screen.queryByRole("button", { name: /SR 210/ })).not.toBeInTheDocument();

    const row = container.querySelector('[data-unresolved="true"]');
    expect(row).not.toBeNull();
    expect(within(row as HTMLElement).getByText("Nicht im Bestand")).toBeInTheDocument();
    expect(
      within(row as HTMLElement).getByText("Die zitierte Norm ist nicht im Bestand."),
    ).toBeInTheDocument();
  });

  it("reports an unresolved citation whose reason was never recorded", () => {
    // Absent reason is a third state: still unresolved, still not a link, and
    // no invented cause.
    const { container } = renderWithProviders(
      <ReferencesTab
        references={[{ direction: "SR", items: [reference({ id: "cit_bare", title: "SR 210" })] }]}
        sourceId="doc_1"
        sourceTitle="Hundegesetz"
      />,
    );

    const row = container.querySelector('[data-unresolved="true"]') as HTMLElement;
    expect(within(row).getByText("Nicht im Bestand")).toBeInTheDocument();
    expect(within(row).getByText("Kein Grund erfasst.")).toBeInTheDocument();
  });

  it("shows an unrecognised reason code rather than swallowing it", () => {
    const { container } = renderWithProviders(
      <ReferencesTab
        references={[
          {
            direction: "SR",
            items: [
              reference({ id: "cit_new", title: "SR 210", unresolvedReason: "target_superseded" }),
            ],
          },
        ]}
        sourceId="doc_1"
        sourceTitle="Hundegesetz"
      />,
    );

    const row = container.querySelector('[data-unresolved="true"]') as HTMLElement;
    expect(within(row).getByText("target_superseded")).toBeInTheDocument();
  });
});
