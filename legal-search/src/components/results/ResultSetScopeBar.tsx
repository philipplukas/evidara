"use client";

import { ChevronLeft } from "lucide-react";
import { useWorkspace } from "@/lib/workspace-store";
import { ActionTextLink } from "../primitives";

export function ResultSetScopeBar() {
  const { state, dispatch } = useWorkspace();
  const canGoBack = state.resultSetStack.length > 0;

  return (
    <div className="flex items-center gap-2 px-5 py-2.5 border-b border-border/60 bg-surface-page/80">
      {canGoBack && (
        <ActionTextLink onClick={() => dispatch({ type: "BACK" })} className="shrink-0">
          <ChevronLeft className="w-3.5 h-3.5" />
          Back
        </ActionTextLink>
      )}
      <span className="text-xs text-muted-foreground truncate">{state.resultSet.scopeLabel}</span>
    </div>
  );
}
