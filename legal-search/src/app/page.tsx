"use client";

import { Suspense } from "react";
import { SearchConstraintsProvider } from "@/lib/search-constraints-store";
import { WorkspaceProvider } from "@/lib/workspace-store";
import WorkspaceClient from "./WorkspaceClient";
import { searchContext, filters, searchResults } from "@/lib/mock-data";

/**
 * Renders the workspace UI wrapped in a Suspense boundary and provider contexts for search constraints and workspace state.
 *
 * @returns The React element tree: a Suspense boundary containing SearchConstraintsProvider, WorkspaceProvider (initialized with mock `initialResults` and `initialQuery`), and the WorkspaceClient with `searchContext` and `filters`.
 */
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
