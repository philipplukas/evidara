import type { Page } from "@playwright/test";

function buildSearchResult(query: string) {
  return {
    id: "decision-1",
    type: "decision",
    title: `Result for ${query}`,
    subtitle: "Federal Supreme Court · Switzerland",
    snippet: "Deterministic test result returned by Playwright route mocks.",
    structuralContext: "Mocked Context",
    badges: [{ label: "Court decision", colorKey: "pink", iconKey: "ch" }],
    metadataRows: [{ label: "Date", value: "2026-04-03" }],
    relatedCounts: [{ label: "Commentary", count: 3 }],
    actions: [{ label: "Open decision", icon: "scale", href: "/documents/decision-1" }],
  };
}

function buildDetail(documentId: string) {
  return {
    id: documentId,
    type: "decision",
    title: "Mocked detail title",
    subtitle: "Mocked detail subtitle",
    breadcrumbs: ["Switzerland", "Federal Supreme Court", documentId],
    metadata: [{ label: "Court", value: "Federal Supreme Court", iconKey: "ch" }],
    content: "Mocked detail content.",
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

export async function mockSearchApi(page: Page) {
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
    const result = buildSearchResult(query);

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        results: [result],
        facets: [],
        totalResults: 1,
      }),
    });
  });

  await page.route("**/v1/documents/*", async (route) => {
    const url = new URL(route.request().url());
    const documentId = url.pathname.split("/").pop() ?? "decision-1";

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(buildDetail(documentId)),
    });
  });
}
