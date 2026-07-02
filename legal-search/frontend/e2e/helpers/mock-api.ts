import type { Page } from "@playwright/test";

function buildSearchResult(query: string, index = 0) {
  const suffix = index === 0 ? "" : ` (${index + 1})`;
  return {
    id: `decision-${index + 1}`,
    type: "decision",
    title: `Result for ${query}${suffix}`,
    subtitle: "Bundesgericht · Schweiz",
    snippet:
      "Das Bundesgericht bestätigt die Verantwortlichkeit der Verwaltungsratsmitglieder gemäss Art. 754 OR. Die Beweislastverteilung richtet sich nach den allgemeinen Grundsätzen.",
    structuralContext: "Obligationenrecht · Gesellschaftsrecht",
    badges: [{ label: "Court decision", colorKey: "pink", iconKey: "ch" }],
    metadataRows: [
      // Fixture dates render as-is (the BFF owns date formatting for
      // MetadataRow.value, per OpenAPI contract). Stay in Swiss DD.MM.YYYY
      // so the result list matches the detail panel and admin date columns
      // in the Sprint 1 screenshot pack.
      { label: "Date", value: "03.04.2026" },
      { label: "Docket", value: "4A_123/2026" },
      { label: "Court", value: "Bundesgericht, I. zivilrechtliche Abteilung" },
    ],
    relatedCounts: [{ label: "Commentary", count: 3 }],
    actions: [{ label: "Open decision", icon: "scale", href: "/documents/decision-1" }],
  };
}

const RICH_FACETS = [
  {
    key: "jurisdiction",
    label: "Jurisdiction",
    type: "chip" as const,
    options: [
      { value: "ch", label: "Switzerland", count: 14523, iconKey: "ch" },
      { value: "at", label: "Austria", count: 8291, iconKey: "at" },
    ],
  },
  {
    key: "court_level",
    label: "Court level",
    type: "checkbox" as const,
    options: [
      { value: "supreme", label: "Supreme Court", count: 4521 },
      { value: "appellate", label: "Appellate Court", count: 3187 },
      { value: "cantonal", label: "Cantonal Court", count: 6892 },
      { value: "district", label: "District Court", count: 2103 },
    ],
  },
  {
    key: "legal_area",
    label: "Legal area",
    type: "checkbox" as const,
    options: [
      { value: "civil", label: "Civil law", count: 8934 },
      { value: "commercial", label: "Commercial law", count: 5621 },
      { value: "corporate", label: "Corporate law", count: 3412 },
      { value: "administrative", label: "Administrative law", count: 2891 },
      { value: "criminal", label: "Criminal law", count: 1843 },
      { value: "constitutional", label: "Constitutional law", count: 1102 },
    ],
  },
  {
    key: "date",
    label: "Date",
    type: "dropdown" as const,
    options: [
      { value: "any", label: "Any time" },
      { value: "1y", label: "Last year" },
      { value: "5y", label: "Last 5 years" },
    ],
  },
  {
    key: "has_commentary",
    label: "Has commentary",
    type: "toggle" as const,
    options: [{ value: "true", label: "Yes" }],
  },
];

function buildDetail(documentId: string) {
  return {
    id: documentId,
    type: "decision",
    title: "BGer 4A_123/2026 — Verantwortlichkeit des Verwaltungsrats",
    subtitle: "Bundesgericht, I. zivilrechtliche Abteilung · Schweiz",
    breadcrumbs: ["Schweiz", "Bundesgericht", documentId],
    metadata: [
      { label: "Court", value: "Bundesgericht", iconKey: "ch" },
      { label: "Date", value: "03.04.2026" },
      { label: "Docket", value: "4A_123/2026" },
    ],
    content: "Das Bundesgericht bestätigt die Verantwortlichkeit der Verwaltungsratsmitglieder gemäss Art. 754 OR.",
    tabs: [
      { key: "details", label: "Details" },
      { key: "related", label: "Related", count: 1 },
      { key: "references", label: "References", count: 1 },
    ],
    relatedGroups: [{ label: "Related decisions", items: [] }],
    references: [{ label: "References", items: [] }],
    annotations: [],
    localStructure: { items: [] },
  };
}

function buildRichDetail(documentId: string) {
  return {
    id: documentId,
    type: "decision",
    title: "BGer 4A_123/2022",
    subtitle: "Verantwortlichkeit des Verwaltungsrats — Beweislastverteilung",
    breadcrumbs: ["Federal Supreme Court", "I. Civil Law Division", "4A_123/2022"],
    metadata: [
      { label: "Court", value: "Federal Supreme Court", iconKey: "ch" },
      { label: "Date", value: "15.03.2022" },
      { label: "Docket", value: "4A_123/2022" },
      { label: "Publication", value: "BGE 148 III 234" },
      { label: "Chamber", value: "I. Civil Law Division" },
      { label: "Outcome", value: "Appeal dismissed" },
    ],
    contentHtml:
      '<div class="decision-text"><p>Art. 754 OR; Verantwortlichkeit der Verwaltungsratsmitglieder; Beweislastverteilung.</p><p>Das Bundesgericht bestätigt, dass die Verantwortlichkeit nach Art. 754 OR eine Pflichtverletzung, einen Schaden, einen Kausalzusammenhang und ein Verschulden voraussetzt.</p></div>',
    tabs: [
      { key: "details", label: "Details" },
      { key: "related", label: "Related", count: 34 },
      { key: "references", label: "References", count: 12 },
      { key: "annotation", label: "Annotation" },
      { key: "structure", label: "Structure" },
    ],
    relatedGroups: [
      {
        label: "Applied norms",
        items: [
          {
            id: "n1",
            title: "Art. 754 OR",
            subtitle: "Haftung der Verwaltung",
            badge: { label: "Law", colorKey: "blue" },
          },
          {
            id: "n2",
            title: "Art. 717 OR",
            subtitle: "Sorgfalts- und Treuepflicht",
            badge: { label: "Law", colorKey: "blue" },
          },
        ],
      },
      {
        label: "Commentary",
        items: [
          {
            id: "c1",
            title: "Basler Kommentar OR II – Art. 754",
            subtitle: "Widmer/Banz · 7th ed. 2023",
            badge: { label: "Commentary", colorKey: "green" },
          },
        ],
      },
    ],
    references: [
      {
        label: "Cited by",
        items: [
          {
            id: "cb1",
            title: "BGer 4A_567/2023",
            subtitle: "Federal Supreme Court · 12.01.2024",
          },
          {
            id: "cb2",
            title: "BGer 4A_890/2022",
            subtitle: "Federal Supreme Court · 05.09.2023",
          },
        ],
      },
      {
        label: "Cites",
        items: [
          {
            id: "ct1",
            title: "BGE 132 III 564",
            subtitle: "Federal Supreme Court · 2006",
          },
          {
            id: "ct2",
            title: "BGE 139 III 24",
            subtitle: "Federal Supreme Court · 2013",
          },
        ],
      },
    ],
    annotations: [
      {
        label: "Article annotation",
        text: "Art. 754 OR regelt die zentrale Haftungsnorm für Gesellschaftsorgane im schweizerischen Aktienrecht.",
      },
    ],
    localStructure: {
      items: [
        { id: "art-752", label: "Art. 752 – Gründungshaftung", active: false },
        { id: "art-753", label: "Art. 753 – Emissionshaftung", active: false },
        { id: "art-754", label: "Art. 754 – Haftung der Verwaltung", active: true },
        { id: "art-755", label: "Art. 755 – Revisionshaftung", active: false },
      ],
    },
  };
}

export interface MockSearchApiOptions {
  richFacets?: boolean;
  richDetail?: boolean;
  /**
   * Number of search results to fabricate per query. Defaults to 1. Set to 0
   * to render the empty state, or to a larger number (e.g. 5) for the
   * multi-result baseline. Visual baselines should use deterministic counts.
   */
  resultCount?: number;
}

export async function mockSearchApi(page: Page, options?: MockSearchApiOptions) {
  const useFacets = options?.richFacets ?? false;
  const useRichDetail = options?.richDetail ?? false;
  const resultCount = options?.resultCount ?? 1;

  await page.route("**/v1/search/context", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        jurisdictions: [{ key: "ch", label: "Switzerland", active: true, iconKey: "ch" }],
        languages: [{ key: "de", label: "DE", active: true }],
        sourceTypes: [{ key: "all", label: "All", active: true }],
        exactMatches: [],
      }),
    });
  });

  await page.route("**/v1/search**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname !== "/v1/search") {
      await route.fallback();
      return;
    }
    const query = url.searchParams.get("q") || "Bundesgericht";
    const results = Array.from({ length: resultCount }, (_, index) =>
      buildSearchResult(query, index),
    );

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        results,
        facets: useFacets ? RICH_FACETS : [],
        totalResults: resultCount,
      }),
    });
  });

  await page.route("**/v1/documents/*", async (route) => {
    const url = new URL(route.request().url());
    const documentId = url.pathname.split("/").pop() ?? "decision-1";

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        useRichDetail ? buildRichDetail(documentId) : buildDetail(documentId),
      ),
    });
  });
}
