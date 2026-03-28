"use client";

import { ChevronLeft } from "lucide-react";
import { useWorkspace } from "@/lib/workspace-store";

export function ResultSetScopeBar() {
  const { state, dispatch } = useWorkspace();
  const canGoBack = state.resultSetStack.length > 0;

  return (
    <div className="flex items-center gap-2 px-5 py-2.5 border-b border-border/60 bg-[#fafafa]/80">
      {canGoBack && (
        <button
          onClick={() => dispatch({ type: "BACK" })}
          className="flex items-center gap-0.5 text-[11px] font-medium text-[#2563eb] hover:text-[#1d4ed8] transition-colors shrink-0"
        >
          <ChevronLeft className="w-3.5 h-3.5" />
          Back
        </button>
      )}
      <span className="text-xs text-muted-foreground truncate">
        {state.resultSet.scopeLabel}
      </span>
    </div>
  );
}
