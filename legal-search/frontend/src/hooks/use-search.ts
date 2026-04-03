"use client";

import { searchDocuments } from "@/lib/api/generated/client";
import type { SearchDocumentsParams } from "@/lib/api/generated/model";
import { mapSearchResponse } from "@/lib/api-adapters";
import type { SearchConstraintsState } from "@/lib/types";

function toSearchParams(query: string, constraints: SearchConstraintsState): SearchDocumentsParams {
  return {
    q: query,
    jurisdiction: constraints.context.jurisdictions[0],
    document_type: constraints.context.sourceType ?? undefined,
  };
}

export async function runSearch(query: string, constraints: SearchConstraintsState) {
  const response = await searchDocuments(toSearchParams(query, constraints));
  if (response.status !== 200) {
    throw new Error("Search request failed.");
  }
  return mapSearchResponse(response.data);
}
