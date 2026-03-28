"use client";

import { Suspense } from "react";
import { WorkspaceProvider } from "@/lib/workspace-store";
import WorkspaceClient from "./WorkspaceClient";
import {
  searchContext,
  filters,
  searchResults,
  articleDetail,
  decisionDetail,
} from "@/lib/mock-data";
import type { DetailViewModel } from "@/lib/types";

const detailMap: Record<string, DetailViewModel> = {
  "law-1": articleDetail,
  "decision-1": decisionDetail,
};

export default function Home() {
  return (
    <WorkspaceProvider
      initialResults={searchResults}
      initialQuery="Art. 754 OR Verantwortlichkeit"
      detailMap={detailMap}
    >
      <Suspense>
        <WorkspaceClient searchContext={searchContext} filters={filters} />
      </Suspense>
    </WorkspaceProvider>
  );
}
