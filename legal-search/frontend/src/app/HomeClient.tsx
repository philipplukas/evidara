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
    return (
      <div className="flex h-screen items-start justify-center bg-surface-page px-4 py-4 sm:px-6">
        <div className="w-full max-w-[1600px] rounded-[2rem] border border-border/60 bg-surface-panel/90 p-4 shadow-[0_18px_56px_rgb(15_23_42/8%)] backdrop-blur-sm sm:p-6">
          <div className="flex flex-col gap-4">
            <div className="h-5 w-32 rounded-full bg-muted/80" />
            <div className="rounded-3xl border border-border/60 bg-surface-input/80 p-3">
              <div className="flex items-center gap-2">
                <div className="h-4 w-4 rounded-full bg-muted/90" />
                <div className="h-4 flex-1 rounded-full bg-muted/70" />
                <div className="h-9 w-20 rounded-xl bg-brand/90" />
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <div className="h-8 w-24 rounded-full bg-muted/80" />
                <div className="h-8 w-28 rounded-full bg-muted/80" />
                <div className="h-8 w-20 rounded-full bg-muted/80" />
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <div className="h-16 rounded-2xl border border-border/60 bg-surface-input/70" />
              <div className="h-16 rounded-2xl border border-border/60 bg-surface-input/70" />
              <div className="h-16 rounded-2xl border border-border/60 bg-surface-input/70 sm:hidden lg:block" />
            </div>
          </div>
        </div>
      </div>
    );
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
