"use client";

import { Suspense } from "react";
import { SearchConstraintsProvider } from "@/lib/search-constraints-store";
import { WorkspaceProvider } from "@/lib/workspace-store";
import WorkspaceClient from "./WorkspaceClient";
import { searchContext, filters, searchResults } from "@/lib/mock-data";

export default function Home() {
  return (
    <SearchConstraintsProvider>
      <WorkspaceProvider
        initialResults={searchResults}
        initialQuery="Art. 754 OR Verantwortlichkeit"
      >
        <Suspense>
          <WorkspaceClient searchContext={searchContext} filters={filters} />
        </Suspense>
      </WorkspaceProvider>
    </SearchConstraintsProvider>
  );
}
