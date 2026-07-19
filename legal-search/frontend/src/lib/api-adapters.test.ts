import { describe, expect, it } from "vitest";
import type { SearchResponseView } from "@/lib/api/generated/model";
import { mapSearchResponse } from "@/lib/api-adapters";

/**
 * The API→view-model boundary. Mocks are authored from the view model, so they
 * cannot disagree with the contract — which is exactly why field drops here
 * (#609 `content`, #615 `totalResults`) survived a full test suite. These tests
 * assert against the *contract* shape rather than a mock.
 */
describe("mapSearchResponse", () => {
  it("carries the hit count across, not the length of the page", () => {
    // The shape the real API returns: 25 matched, one page of 2 returned.
    const response: SearchResponseView = {
      results: [
        {
          id: "doc-1",
          title: "Art. 754 OR",
          subtitle: "Verantwortlichkeit",
          snippet: "…",
          type: "law",
          badges: [],
          metadataRows: [],
          relatedCounts: [],
          actions: [],
        },
        {
          id: "doc-2",
          title: "Art. 756 OR",
          subtitle: "Klagerecht",
          snippet: "…",
          type: "law",
          badges: [],
          metadataRows: [],
          relatedCounts: [],
          actions: [],
        },
      ],
      facets: [],
      totalResults: 25,
    };

    const mapped = mapSearchResponse(response);

    // Dropping this is #615: the UI then counts the array and tells the user a
    // 25-hit search found 2.
    expect(mapped.totalResults).toBe(25);
    expect(mapped.results).toHaveLength(2);
  });
});
