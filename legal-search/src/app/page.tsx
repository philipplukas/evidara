"use client";

import { Suspense } from "react";
import { filters, searchContext, searchResults } from "@/lib/mock-data";
import { SearchConstraintsProvider } from "@/lib/search-constraints-store";
import { WorkspaceProvider } from "@/lib/workspace-store";
import WorkspaceClient from "./WorkspaceClient";

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
