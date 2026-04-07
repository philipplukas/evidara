"use client";

import {
  createContext,
  type Dispatch,
  type ReactNode,
  useContext,
  useEffect,
  useReducer,
} from "react";
import type {
  PinnedItem,
  ResultSet,
  ResultSetSource,
  SearchResultViewModel,
  TrailEntry,
} from "./types";

// ─── Actions ───

export type WorkspaceAction =
  | { type: "SEARCH"; query: string; results: SearchResultViewModel[] }
  | { type: "RESET_FROM_BOOT"; query: string; results: SearchResultViewModel[] }
  | {
      type: "PIVOT";
      source: ResultSetSource;
      results: SearchResultViewModel[];
      scopeLabel: string;
    }
  | { type: "BACK" }
  | { type: "PUSH_TRAIL"; entry: TrailEntry }
  | { type: "CLEAR_TRAIL" }
  | { type: "PIN"; item: PinnedItem }
  | { type: "UNPIN"; id: string };

// ─── State ───

interface WorkspaceState {
  /** The current visible result set in the center column */
  resultSet: ResultSet;
  /** Stack of previous result sets (for BACK navigation) */
  resultSetStack: ResultSet[];
  /** Navigation trail: items the user has focused on */
  trail: TrailEntry[];
  /** Pinned items persisted across pivots */
  pinned: PinnedItem[];
}

function createInitialState(results: SearchResultViewModel[], query: string): WorkspaceState {
  return {
    resultSet: {
      source: { type: "search", query },
      items: results,
      scopeLabel: `Results for "${query}"`,
    },
    resultSetStack: [],
    trail: [],
    pinned: [],
  };
}

// ─── Reducer ───

function workspaceReducer(state: WorkspaceState, action: WorkspaceAction): WorkspaceState {
  switch (action.type) {
    case "SEARCH":
    case "RESET_FROM_BOOT":
      return {
        ...state,
        resultSet: {
          source: { type: "search", query: action.query },
          items: action.results,
          scopeLabel: `Results for "${action.query}"`,
        },
        resultSetStack: [],
        trail: [],
      };

    case "PIVOT":
      return {
        ...state,
        resultSetStack: [...state.resultSetStack, state.resultSet],
        resultSet: {
          source: action.source,
          items: action.results,
          scopeLabel: action.scopeLabel,
        },
      };

    case "BACK": {
      if (state.resultSetStack.length === 0) return state;
      const previous = state.resultSetStack[state.resultSetStack.length - 1];
      return {
        ...state,
        resultSet: previous,
        resultSetStack: state.resultSetStack.slice(0, -1),
      };
    }

    case "PUSH_TRAIL":
      return {
        ...state,
        trail: [...state.trail, action.entry],
      };

    case "CLEAR_TRAIL":
      return {
        ...state,
        trail: [],
      };

    case "PIN": {
      if (state.pinned.some((p) => p.id === action.item.id)) return state;
      return {
        ...state,
        pinned: [...state.pinned, action.item],
      };
    }

    case "UNPIN":
      return {
        ...state,
        pinned: state.pinned.filter((p) => p.id !== action.id),
      };

    default:
      return state;
  }
}

// ─── Context ───

interface WorkspaceContextValue {
  state: WorkspaceState;
  dispatch: Dispatch<WorkspaceAction>;
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export function useWorkspace(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace must be used within a WorkspaceProvider");
  return ctx;
}

interface WorkspaceProviderProps {
  children: ReactNode;
  initialResults: SearchResultViewModel[];
  initialQuery: string;
}

export function WorkspaceProvider({
  children,
  initialResults,
  initialQuery,
}: WorkspaceProviderProps) {
  const [state, dispatch] = useReducer(
    workspaceReducer,
    createInitialState(initialResults, initialQuery),
  );

  useEffect(() => {
    dispatch({
      type: "RESET_FROM_BOOT",
      query: initialQuery,
      results: initialResults,
    });
  }, [initialQuery, initialResults]);

  return (
    <WorkspaceContext.Provider value={{ state, dispatch }}>{children}</WorkspaceContext.Provider>
  );
}
