"use client";

import { parseAsArrayOf, parseAsBoolean, parseAsString, useQueryStates } from "nuqs";
import { createContext, type Dispatch, type ReactNode, useContext, useMemo } from "react";
import type { ContextConstraints, SearchConstraintsState, SearchRefinement } from "./types";

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

const SearchConstraintsContext = createContext<SearchConstraintsContextValue | null>(null);

// Supported filter keys and their valid values
const SUPPORTED_FILTERS = {
  jurisdiction: ["ch", "at"],
  language: ["de", "fr", "it", "en"],
  document_type: ["law", "decision", "rechtssatz", "commentary"],
  court_level: ["supreme", "appellate", "cantonal", "district"],
  legal_area: ["civil", "commercial", "corporate", "administrative", "criminal", "constitutional"],
  date: ["any", "1y", "5y", "10y"],
  has_commentary: ["true"],
  has_decisions: ["true"],
} as const;

const SUPPORTED_REFINEMENT_TYPES = ["terms", "date_range", "range", "toggle", "text"] as const;

type SupportedFilterKey = keyof typeof SUPPORTED_FILTERS;

function isSupportedFilterKey(key: string): key is SupportedFilterKey {
  return key in SUPPORTED_FILTERS;
}

function normalizeAndValidateValues(field: string, values: string[]): string[] {
  if (!isSupportedFilterKey(field)) return [];

  const supportedValues = SUPPORTED_FILTERS[field];
  const normalizedValues: string[] = [];

  for (const value of values) {
    const normalized = value.toLowerCase().trim();
    if (supportedValues.includes(normalized as never)) {
      normalizedValues.push(normalized);
    }
  }

  return normalizedValues;
}

// Supported source types
const SUPPORTED_SOURCE_TYPES = ["all", "law", "decision", "rechtssatz", "commentary"] as const;

function normalizeJurisdictions(jurisdictions: string[]): string[] {
  const validated = normalizeAndValidateValues("jurisdiction", jurisdictions);
  // Ensure at least one jurisdiction is selected, default to CH
  return validated.length > 0 ? validated : ["ch"];
}

function normalizeLanguages(languages: string[]): string[] {
  const validated = normalizeAndValidateValues("language", languages);
  // Ensure at least one language is selected, default to de
  return validated.length > 0 ? validated : ["de"];
}

function normalizeSourceType(sourceType: string | null): string | null {
  if (!sourceType) return null;
  const normalized = sourceType.toLowerCase().trim();
  return SUPPORTED_SOURCE_TYPES.includes(normalized as never) ? normalized : null;
}

function parseRefinements(serialized: string | null): SearchRefinement[] {
  if (!serialized) return [];

  try {
    const parsed = JSON.parse(serialized);
    if (!Array.isArray(parsed)) return [];

    return parsed
      .filter((refinement): refinement is SearchRefinement => {
        if (typeof refinement !== "object" || refinement === null) return false;
        const candidate = refinement as Partial<SearchRefinement>;
        return (
          typeof candidate.field === "string" &&
          typeof candidate.type === "string" &&
          Array.isArray(candidate.values)
        );
      })
      .map((refinement) => {
        // Validate refinement type
        if (!SUPPORTED_REFINEMENT_TYPES.includes(refinement.type as never)) {
          return null;
        }

        // Validate field and normalize values
        const normalizedValues = normalizeAndValidateValues(refinement.field, refinement.values);

        // Drop refinements with no valid values
        if (normalizedValues.length === 0) {
          return null;
        }

        return {
          ...refinement,
          values: normalizedValues,
        };
      })
      .filter((refinement): refinement is SearchRefinement => refinement !== null);
  } catch {
    return [];
  }
}

function serializeRefinements(refinements: SearchRefinement[]): string {
  return JSON.stringify(refinements);
}

function toggleValue(values: string[], value: string): string[] {
  return values.includes(value) ? values.filter((v) => v !== value) : [...values, value];
}

export function useSearchConstraints(): SearchConstraintsContextValue {
  const ctx = useContext(SearchConstraintsContext);
  if (!ctx) {
    throw new Error("useSearchConstraints must be used within a SearchConstraintsProvider");
  }
  return ctx;
}

interface SearchConstraintsProviderProps {
  children: ReactNode;
}

export function SearchConstraintsProvider({ children }: SearchConstraintsProviderProps) {
  const [urlState, setUrlState] = useQueryStates({
    jurisdictions: parseAsArrayOf(parseAsString).withDefault(["CH"]),
    languages: parseAsArrayOf(parseAsString).withDefault(["de"]),
    sourceType: parseAsString,
    officialOnly: parseAsBoolean.withDefault(false),
    refinements: parseAsString,
  });

  const refinements = useMemo(() => parseRefinements(urlState.refinements), [urlState.refinements]);

  const normalizedJurisdictions = useMemo(
    () => normalizeJurisdictions(urlState.jurisdictions),
    [urlState.jurisdictions],
  );

  const normalizedLanguages = useMemo(
    () => normalizeLanguages(urlState.languages),
    [urlState.languages],
  );

  const normalizedSourceType = useMemo(
    () => normalizeSourceType(urlState.sourceType),
    [urlState.sourceType],
  );

  const state: SearchConstraintsState = useMemo(
    () => ({
      context: {
        jurisdictions: normalizedJurisdictions,
        languages: normalizedLanguages,
        sourceType: normalizedSourceType,
        officialOnly: urlState.officialOnly,
      } satisfies ContextConstraints,
      refinements,
    }),
    [
      normalizedJurisdictions,
      normalizedLanguages,
      normalizedSourceType,
      urlState.officialOnly,
      refinements,
    ],
  );

  const dispatch = useMemo<Dispatch<SearchConstraintsAction>>(
    () => (action) => {
      switch (action.type) {
        case "TOGGLE_JURISDICTION":
          void setUrlState({
            jurisdictions: toggleValue(state.context.jurisdictions, action.jurisdiction),
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
          const existing = state.refinements.filter((r) => r.field !== action.field);
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
    [setUrlState, state.context.jurisdictions, state.context.languages, state.refinements],
  );

  return (
    <SearchConstraintsContext.Provider value={{ state, dispatch }}>
      {children}
    </SearchConstraintsContext.Provider>
  );
}
