"use client";

import {
  createContext,
  useContext,
  useReducer,
  type ReactNode,
  type Dispatch,
} from "react";
import type {
  ContextConstraints,
  SearchRefinement,
  SearchConstraintsState,
} from "./types";

// ─── Actions ───

export type SearchConstraintsAction =
  | { type: "TOGGLE_JURISDICTION"; jurisdiction: string }
  | { type: "TOGGLE_LANGUAGE"; language: string }
  | { type: "SET_SOURCE_TYPE"; sourceType: string | null }
  | { type: "SET_OFFICIAL_ONLY"; value: boolean }
  | { type: "SET_REFINEMENT"; field: string; refinement: SearchRefinement }
  | { type: "CLEAR_REFINEMENT"; field: string }
  | { type: "CLEAR_ALL_REFINEMENTS" }
  | { type: "RESET_ALL" };

// ─── Initial State ───

function createInitialContext(): ContextConstraints {
  return {
    jurisdictions: ["CH"],
    languages: ["de"],
    sourceType: null,
    officialOnly: false,
  };
}

function createInitialState(): SearchConstraintsState {
  return {
    context: createInitialContext(),
    refinements: [],
  };
}

// ─── Reducer ───

function searchConstraintsReducer(
  state: SearchConstraintsState,
  action: SearchConstraintsAction
): SearchConstraintsState {
  switch (action.type) {
    case "TOGGLE_JURISDICTION": {
      const current = state.context.jurisdictions;
      const next = current.includes(action.jurisdiction)
        ? current.filter((j) => j !== action.jurisdiction)
        : [...current, action.jurisdiction];
      return {
        ...state,
        context: { ...state.context, jurisdictions: next },
      };
    }

    case "TOGGLE_LANGUAGE": {
      const current = state.context.languages;
      const next = current.includes(action.language)
        ? current.filter((l) => l !== action.language)
        : [...current, action.language];
      return {
        ...state,
        context: { ...state.context, languages: next },
      };
    }

    case "SET_SOURCE_TYPE":
      return {
        ...state,
        context: { ...state.context, sourceType: action.sourceType },
      };

    case "SET_OFFICIAL_ONLY":
      return {
        ...state,
        context: { ...state.context, officialOnly: action.value },
      };

    case "SET_REFINEMENT": {
      const existing = state.refinements.filter(
        (r) => r.field !== action.field
      );
      return {
        ...state,
        refinements: [...existing, action.refinement],
      };
    }

    case "CLEAR_REFINEMENT":
      return {
        ...state,
        refinements: state.refinements.filter(
          (r) => r.field !== action.field
        ),
      };

    case "CLEAR_ALL_REFINEMENTS":
      return {
        ...state,
        refinements: [],
      };

    case "RESET_ALL":
      return createInitialState();

    default:
      return state;
  }
}

// ─── Context ───

interface SearchConstraintsContextValue {
  state: SearchConstraintsState;
  dispatch: Dispatch<SearchConstraintsAction>;
}

const SearchConstraintsContext =
  createContext<SearchConstraintsContextValue | null>(null);

export function useSearchConstraints(): SearchConstraintsContextValue {
  const ctx = useContext(SearchConstraintsContext);
  if (!ctx)
    throw new Error(
      "useSearchConstraints must be used within a SearchConstraintsProvider"
    );
  return ctx;
}

// ─── Provider ───

interface SearchConstraintsProviderProps {
  children: ReactNode;
}

export function SearchConstraintsProvider({
  children,
}: SearchConstraintsProviderProps) {
  const [state, dispatch] = useReducer(
    searchConstraintsReducer,
    undefined,
    createInitialState
  );

  return (
    <SearchConstraintsContext.Provider value={{ state, dispatch }}>
      {children}
    </SearchConstraintsContext.Provider>
  );
}
