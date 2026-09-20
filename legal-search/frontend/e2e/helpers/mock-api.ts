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
    // `visibility` is REQUIRED on a detail metadata row (#787). The BFF sets it
    // on every row it emits; a mock that omits it is not a smaller response,
    // it is a shape the API cannot produce — and the glance strip (compact
    // density) would silently render nothing.
    metadata: [
      { label: "Court", value: "Bundesgericht", iconKey: "ch", visibility: "always" },
      { label: "Date", value: "03.04.2026", visibility: "always" },
      { label: "Docket", value: "4A_123/2026", visibility: "default" },
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
    // See buildDetail: `visibility` is required, and these values reproduce
    // exactly what the deleted label heuristics resolved for a `decision`, so
    // the visual baselines are unchanged by #787.
    metadata: [
      { label: "Court", value: "Federal Supreme Court", iconKey: "ch", visibility: "always" },
      { label: "Date", value: "15.03.2022", visibility: "always" },
      { label: "Docket", value: "4A_123/2022", visibility: "default" },
      { label: "Publication", value: "BGE 148 III 234", visibility: "default" },
      { label: "Chamber", value: "I. Civil Law Division", visibility: "default" },
      { label: "Outcome", value: "Appeal dismissed", visibility: "always" },
    ],
    // `content` — the field the API actually sends, carrying plain text.
    // This mock used to emit `contentHtml`, which is a *view-model* field that
    // has never existed on an API response: `mapDetail()` dropped it here for
    // the same reason it dropped the body in production, so these e2e runs and
    // their visual baselines were captured with no document text at all (#609).
    content:
      "Art. 754 OR; Verantwortlichkeit der Verwaltungsratsmitglieder; Beweislastverteilung.\n\nDas Bundesgericht bestätigt, dass die Verantwortlichkeit nach Art. 754 OR eine Pflichtverletzung, einen Schaden, einen Kausalzusammenhang und ein Verschulden voraussetzt.",
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
    // `citation` and `resolved` are what `ReferenceItem` requires; `subtitle`
    // was a key no API response has ever sent, so these rows used to render
    // their titles alone (#1040). `ct2` is unresolved on purpose — the
    // dead-reference state needs a browser-level fixture too.
    references: [
      {
        label: "Cited by",
        items: [
          {
            id: "cb1",
            title: "BGer 4A_567/2023",
            citation: "Federal Supreme Court · 12.01.2024",
            resolved: true,
            targetDocumentId: "decision-cb1",
            href: "/documents/decision-cb1",
          },
          {
            id: "cb2",
            title: "BGer 4A_890/2022",
            citation: "Federal Supreme Court · 05.09.2023",
            resolved: true,
            targetDocumentId: "decision-cb2",
            href: "/documents/decision-cb2",
          },
        ],
      },
      {
        label: "Cites",
        items: [
          {
            id: "ct1",
            title: "BGE 132 III 564",
            citation: "Federal Supreme Court · 2006",
            resolved: true,
            targetDocumentId: "decision-ct1",
            href: "/documents/decision-ct1",
          },
          {
            id: "ct2",
            title: "BGE 139 III 24",
            citation: "Federal Supreme Court · 2013",
            resolved: false,
            unresolvedReason: "no_target_in_corpus",
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
    // `depth` and `text` are what make this an outline rather than a list of
    // labels. None of these titles occurs in this fixture's two-paragraph
    // `content`, so none of them anchors — which is the correct outcome and
    // the reason the details-tab visual baselines are unchanged by #1040.
    localStructure: {
      items: [
        { id: "art-752", label: "Art. 752 – Gründungshaftung", active: false, depth: 0 },
        { id: "art-753", label: "Art. 753 – Emissionshaftung", active: false, depth: 0 },
        { id: "art-754", label: "Art. 754 – Haftung der Verwaltung", active: true, depth: 0 },
        { id: "art-755", label: "Art. 755 – Revisionshaftung", active: false, depth: 1 },
      ],
    },
  };
}

/**
 * A statute the reading surface can actually be measured against (#1053).
 *
 * `buildDetail` and `buildRichDetail` both predate reading mode and neither
 * carries what it needs: no `content` tab, and outlines whose titles do not
 * occur in the body, so nothing anchors and there is nothing to scroll
 * between. This one is shaped like the ZH Hundegesetz as the BFF sends it —
 * a `content` tab, section titles that appear in the body as their own
 * paragraphs (so `buildDocumentOutline` places them), nested depths, and one
 * citation the corpus holds beside one it does not.
 *
 * The paragraphs are long on purpose: a characters-per-line measurement needs
 * lines that wrap, and a two-sentence fixture measures the fixture rather than
 * the column.
 */
function buildReaderDetail(documentId: string) {
  const paragraph = (lead: string) =>
    `${lead} Die zustaendige Behoerde beruecksichtigt dabei die oertlichen Verhaeltnisse, die Zahl der gehaltenen Tiere und die Sicherheit der uebrigen Bevoelkerung, und sie hoert die betroffenen Gemeinden an, bevor sie eine Anordnung trifft, die ueber den Einzelfall hinausreicht und allgemeine Geltung beansprucht.`;

  return {
    id: documentId,
    type: "law",
    title: "Hundegesetz",
    subtitle: "Kanton Zuerich, in Kraft seit 01.01.2010",
    breadcrumbs: ["Kanton Zuerich", "Ordnungsrecht", "Tierhaltung"],
    metadata: [
      { label: "Rechtsordnung", value: "Kanton Zuerich", iconKey: "ch", visibility: "always" },
      { label: "In Kraft", value: "01.01.2010", visibility: "always" },
      { label: "Fundstelle", value: "LS 554.5", visibility: "default" },
    ],
    content: [
      "I. Allgemeine Bestimmungen",
      paragraph("Dieses Gesetz regelt die Haltung von Hunden im Kanton Zuerich."),
      "§ 1 Meldepflicht",
      paragraph("Wer einen Hund haelt, meldet ihn innert zehn Tagen der Wohnsitzgemeinde."),
      "§ 2 Leinenpflicht",
      paragraph("Der Gemeinderat kann fuer bestimmte Gebiete eine Leinenpflicht anordnen."),
      "II. Strafbestimmungen",
      paragraph("Widerhandlungen gegen dieses Gesetz werden mit Busse bestraft."),
      "§ 9 Vollzug",
      paragraph("Der Regierungsrat erlaesst die Ausfuehrungsbestimmungen zu diesem Gesetz."),
    ].join("\n\n"),
    tabs: [
      { key: "content", label: "Inhalt" },
      { key: "sections", label: "Abschnitte", count: 6 },
      { key: "citations", label: "Verweise", count: 2 },
      { key: "details", label: "Details" },
    ],
    relatedGroups: [],
    references: [
      {
        label: "SR",
        items: [
          {
            id: "cit_tschg",
            title: "Tierschutzgesetz",
            citation: "SR 455.1",
            resolved: true,
            targetDocumentId: "decision-1",
            href: "/documents/decision-1",
          },
          {
            id: "cit_zgb",
            title: "SR 210",
            citation: "SR 210 Art. 641",
            resolved: false,
            unresolvedReason: "no_target_in_corpus",
          },
        ],
      },
    ],
    annotations: [],
    localStructure: {
      items: [
        { id: "sec_1", label: "I. Allgemeine Bestimmungen", active: false, depth: 0 },
        { id: "sec_2", label: "§ 1 Meldepflicht", active: false, depth: 1 },
        { id: "sec_3", label: "§ 2 Leinenpflicht", active: false, depth: 1 },
        { id: "sec_4", label: "II. Strafbestimmungen", active: false, depth: 0 },
        { id: "sec_5", label: "§ 9 Vollzug", active: false, depth: 1 },
        // Published in the outline, absent from the body. It must render as
        // text and not as a control — accepting a click and scrolling nowhere
        // is indistinguishable from a jump that worked (#1040).
        { id: "sec_6", label: "§ 10 Uebergangsrecht", active: false, depth: 1 },
      ],
    },
  };
}

export interface MockSearchApiOptions {
  richFacets?: boolean;
  richDetail?: boolean;
  /** The statute fixture reading mode is measured against. See above. */
  readerDetail?: boolean;
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
  const useReaderDetail = options?.readerDetail ?? false;
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
        useReaderDetail
          ? buildReaderDetail(documentId)
          : useRichDetail
            ? buildRichDetail(documentId)
            : buildDetail(documentId),
      ),
    });
  });
}
