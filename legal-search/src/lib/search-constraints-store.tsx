"use client";

import {
  createContext,
  useContext,
  useMemo,
  type ReactNode,
  type Dispatch,
} from "react";
import {
  parseAsBoolean,
  parseAsString,
  parseAsArrayOf,
  useQueryStates,
} from "nuqs";
import type {
  ContextConstraints,
  SearchRefinement,
  SearchConstraintsState,
} from "./types";

export type SearchConstraintsAction =
  | { type: "TOGGLE_JURISDICTION"; jurisdiction: string }
  | { type: "TOGGLE_LANGUAGE"; language: string }
  | { type: "SET_SOURCE_TYPE"; sourceType: string | null }
  | { type: "SET_OFFICIAL_ONLY"; value: boolean }
  | { type: "SET_REFINEMENT"; field: string; refinement: SearchRefinement }
  | { type: "CLEAR_REFINEMENT"; field: string }
  | { type: "CLEAR_ALL_REFINEMENTS" }
  | { type: "RESET_ALL" };

interface SearchConstraintsContextValue {
  state: SearchConstraintsState;
  dispatch: Dispatch<SearchConstraintsAction>;
}

const SearchConstraintsContext =
  createContext<SearchConstraintsContextValue | null>(null);

/**
 * Parse a URL-serialized refinements string into a validated array of search refinements.
 *
 * Parses the JSON `serialized` value and returns only elements that are objects with a string
 * `field`, a string `type`, and an array `values`. If `serialized` is falsy, is not valid JSON,
 * is not an array, or contains no valid refinement objects, an empty array is returned.
 *
 * @param serialized - A JSON string from the URL representing refinements, or `null`
 * @returns An array of validated `SearchRefinement` objects; empty if the input is missing or invalid
 */
function parseRefinements(serialized: string | null): SearchRefinement[] {
  if (!serialized) return [];

  try {
    const parsed = JSON.parse(serialized);
    if (!Array.isArray(parsed)) return [];

    return parsed.filter((refinement): refinement is SearchRefinement => {
      if (typeof refinement !== "object" || refinement === null) return false;
      const candidate = refinement as Partial<SearchRefinement>;
      return (
        typeof candidate.field === "string" &&
        typeof candidate.type === "string" &&
        Array.isArray(candidate.values)
      );
    });
  } catch {
    return [];
  }
}

/**
 * Serialize an array of search refinements into a JSON string.
 *
 * @param refinements - The refinements to serialize
 * @returns The JSON string representation of `refinements`
 */
function serializeRefinements(refinements: SearchRefinement[]): string {
  return JSON.stringify(refinements);
}

/**
 * Toggle the presence of a string in an array of strings.
 *
 * @param values - The source array of strings
 * @param value - The string to add or remove
 * @returns A new array with `value` removed if it was present, or appended if it was absent
 */
function toggleValue(values: string[], value: string): string[] {
  return values.includes(value)
    ? values.filter((v) => v !== value)
    : [...values, value];
}

/**
 * Accesses the current search constraints context.
 *
 * @returns The `SearchConstraintsContextValue` containing the current `state` and `dispatch`.
 * @throws Error if the hook is used outside a `SearchConstraintsProvider`.
 */
export function useSearchConstraints(): SearchConstraintsContextValue {
  const ctx = useContext(SearchConstraintsContext);
  if (!ctx) {
    throw new Error(
      "useSearchConstraints must be used within a SearchConstraintsProvider"
    );
  }
  return ctx;
}

interface SearchConstraintsProviderProps {
  children: ReactNode;
}

/**
 * Provides URL-synchronized search constraints state and a dispatcher to update it to descendant components.
 *
 * The provider keeps jurisdictions, languages, sourceType, officialOnly, and refinements synchronized with the URL
 * query state and exposes a `state` and `dispatch` pair via SearchConstraintsContext.
 *
 * @param children - React nodes to render within the provider
 * @returns A React context provider element that supplies the current search constraints state and a dispatch function
 */
export function SearchConstraintsProvider({
  children,
}: SearchConstraintsProviderProps) {
  const [urlState, setUrlState] = useQueryStates({
    jurisdictions: parseAsArrayOf(parseAsString).withDefault(["CH"]),
    languages: parseAsArrayOf(parseAsString).withDefault(["de"]),
    sourceType: parseAsString,
    officialOnly: parseAsBoolean.withDefault(false),
    refinements: parseAsString,
  });

  const refinements = useMemo(
    () => parseRefinements(urlState.refinements),
    [urlState.refinements]
  );

  const state: SearchConstraintsState = useMemo(
    () => ({
      context: {
        jurisdictions: urlState.jurisdictions,
        languages: urlState.languages,
        sourceType: urlState.sourceType,
        officialOnly: urlState.officialOnly,
      } satisfies ContextConstraints,
      refinements,
    }),
    [
      urlState.jurisdictions,
      urlState.languages,
      urlState.sourceType,
      urlState.officialOnly,
      refinements,
    ]
  );

  const dispatch = useMemo<Dispatch<SearchConstraintsAction>>(
    () => (action) => {
      switch (action.type) {
        case "TOGGLE_JURISDICTION":
          void setUrlState({
            jurisdictions: toggleValue(
              state.context.jurisdictions,
              action.jurisdiction
            ),
          });
          break;

        case "TOGGLE_LANGUAGE":
          void setUrlState({
            languages: toggleValue(state.context.languages, action.language),
          });
          break;

        case "SET_SOURCE_TYPE":
          void setUrlState({ sourceType: action.sourceType });
          break;

        case "SET_OFFICIAL_ONLY":
          void setUrlState({ officialOnly: action.value });
          break;

        case "SET_REFINEMENT": {
          const existing = state.refinements.filter(
            (r) => r.field !== action.field
          );
          void setUrlState({
            refinements: serializeRefinements([...existing, action.refinement]),
          });
          break;
        }

        case "CLEAR_REFINEMENT": {
          const next = state.refinements.filter((r) => r.field !== action.field);
          void setUrlState({
            refinements: next.length > 0 ? serializeRefinements(next) : null,
          });
          break;
        }

        case "CLEAR_ALL_REFINEMENTS":
          void setUrlState({ refinements: null });
          break;

        case "RESET_ALL":
          void setUrlState({
            jurisdictions: ["CH"],
            languages: ["de"],
            sourceType: null,
            officialOnly: false,
            refinements: null,
          });
          break;

        default:
          break;
      }
    },
    [setUrlState, state.context.jurisdictions, state.context.languages, state.refinements]
  );

  return (
    <SearchConstraintsContext.Provider value={{ state, dispatch }}>
      {children}
    </SearchConstraintsContext.Provider>
  );
}
