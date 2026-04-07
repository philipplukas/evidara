import { describe, expect, it, vi } from "vitest";
import { runSearch } from "@/hooks/use-search";

const searchDocumentsMock = vi.fn();
const mapSearchResponseMock = vi.fn();

vi.mock("@/lib/api/generated/client", () => ({
  searchDocuments: (params: unknown) => searchDocumentsMock(params),
}));

vi.mock("@/lib/api-adapters", () => ({
  mapSearchResponse: (payload: unknown) => mapSearchResponseMock(payload),
}));

describe("runSearch", () => {
  it("maps constraints into search request params", async () => {
    searchDocumentsMock.mockResolvedValueOnce({
      status: 200,
      data: { results: [], facets: [], totalResults: 0 },
    });
    mapSearchResponseMock.mockReturnValueOnce({ results: [], filters: [] });

    await runSearch("Art. 754", {
      context: {
        jurisdictions: ["ch", "at"],
        languages: ["de", "fr"],
        sourceType: "law",
        officialOnly: true,
      },
      refinements: [{ field: "court_level", type: "terms", values: ["supreme"] }],
    });

    expect(searchDocumentsMock).toHaveBeenCalledWith({
      q: "Art. 754",
      jurisdictions: "ch,at",
      languages: "de,fr",
      document_types: "law",
      official_only: true,
      refinements: JSON.stringify([{ field: "court_level", type: "terms", values: ["supreme"] }]),
    });
  });
});
