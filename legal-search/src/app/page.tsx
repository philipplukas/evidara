"use client";

import { Suspense } from "react";
import { filters, searchContext, searchResults } from "@/lib/mock-data";
import { SearchConstraintsProvider } from "@/lib/search-constraints-store";
import { WorkspaceProvider } from "@/lib/workspace-store";
import WorkspaceClient from "./WorkspaceClient";

export default function Home() {
  return (
    <Suspense>
      <SearchConstraintsProvider>
        <WorkspaceProvider
          initialResults={searchResults}
          initialQuery="Art. 754 OR Verantwortlichkeit"
        >
          <WorkspaceClient searchContext={searchContext} filters={filters} />
        </WorkspaceProvider>
      </SearchConstraintsProvider>
    </Suspense>
  );
}
