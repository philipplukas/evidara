"use client";

import { searchDocuments } from "@/lib/api/generated/client";
import type { SearchDocumentsParams } from "@/lib/api/generated/model";
import { mapSearchResponse } from "@/lib/api-adapters";
import type { SearchConstraintsState } from "@/lib/types";

function toSearchParams(query: string, constraints: SearchConstraintsState): SearchDocumentsParams {
  const documentTypes = constraints.context.sourceType
    ? [constraints.context.sourceType]
    : undefined;

  return {
    q: query,
    jurisdictions: constraints.context.jurisdictions.join(","),
    languages: constraints.context.languages.join(","),
    document_types: documentTypes?.join(","),
    official_only: constraints.context.officialOnly,
    refinements:
      constraints.refinements.length > 0 ? JSON.stringify(constraints.refinements) : undefined,
  };
}

export async function runSearch(query: string, constraints: SearchConstraintsState) {
  const response = await searchDocuments(toSearchParams(query, constraints));
  if (response.status !== 200) {
    throw new Error("Search request failed.");
  }
  return mapSearchResponse(response.data);
}
