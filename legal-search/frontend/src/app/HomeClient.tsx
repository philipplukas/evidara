"use client";

import { parseAsString, useQueryState } from "nuqs";
import { Suspense, useEffect, useState } from "react";
import { getSearchContext, searchDocuments } from "@/lib/api/generated/client";
import { mapSearchContext, mapSearchResponse } from "@/lib/api-adapters";
import { SearchConstraintsProvider } from "@/lib/search-constraints-store";
import type { FilterViewModel, SearchContextViewModel, SearchResultViewModel } from "@/lib/types";
import { WorkspaceProvider } from "@/lib/workspace-store";
import WorkspaceClient from "./WorkspaceClient";

const DEFAULT_QUERY = "Art. 754 OR Verantwortlichkeit";

interface HomeClientProps {
  showControlPlaneEntry: boolean;
  controlPanelUrl?: string;
}

export default function HomeClient({ showControlPlaneEntry, controlPanelUrl }: HomeClientProps) {
  const [urlQuery] = useQueryState("q", parseAsString.withDefault(DEFAULT_QUERY));
  const [bootState, setBootState] = useState<{
    searchContext: SearchContextViewModel;
    filters: FilterViewModel[];
    results: SearchResultViewModel[];
  } | null>(null);

  useEffect(() => {
    let active = true;

    const load = async () => {
      const [contextResponse, searchResponse] = await Promise.all([
        getSearchContext(),
        searchDocuments({ q: urlQuery }),
      ]);

      if (!active) return;
      if (contextResponse.status !== 200 || searchResponse.status !== 200) {
        setBootState({
          searchContext: { jurisdictions: [], languages: [], sourceTypes: [], exactMatches: [] },
          filters: [],
          results: [],
        });
        return;
      }

      const mappedContext = mapSearchContext(contextResponse.data);
      const mappedSearch = mapSearchResponse(searchResponse.data);
      setBootState({
        searchContext: mappedContext,
        filters: mappedSearch.filters,
        results: mappedSearch.results,
      });
    };

    void load();
    return () => {
      active = false;
    };
  }, [urlQuery]);

  if (!bootState) {
    return <div className="h-screen bg-surface-page" />;
  }

  return (
    <Suspense>
      <SearchConstraintsProvider>
        <WorkspaceProvider initialResults={bootState.results} initialQuery={urlQuery}>
          <WorkspaceClient
            searchContext={bootState.searchContext}
            filters={bootState.filters}
            showControlPlaneEntry={showControlPlaneEntry}
            controlPanelUrl={controlPanelUrl}
          />
        </WorkspaceProvider>
      </SearchConstraintsProvider>
    </Suspense>
  );
}
