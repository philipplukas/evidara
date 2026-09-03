"use client";

import { useQueryStates } from "nuqs";
import {
  createContext,
  type Dispatch,
  type ReactNode,
  useCallback,
  useContext,
  useMemo,
  useRef,
} from "react";
import { DEFAULT_JURISDICTIONS, DEFAULT_LANGUAGES, searchParamsParsers } from "./search-params";
import type { ContextConstraints, SearchConstraintsState, SearchRefinement } from "./types";

export type SearchConstraintsAction =
  | { type: "TOGGLE_JURISDICTION"; jurisdiction: string }
  | { type: "TOGGLE_LANGUAGE"; language: string }
  | { type: "SET_SOURCE_TYPE"; sourceType: string | null }
  | { type: "SET_OFFICIAL_ONLY"; value: boolean }
  | { type: "SET_REFINEMENT"; field: string; refinement: SearchRefinement }
  | { type: "CLEAR_REFINEMENT"; field: string }
  | { type: "CLEAR_ALL_REFINEMENTS" }
  | { type: "RESET_ALL" }
  | { type: "UNDO_RESET" };

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
  // Ensure at least one jurisdiction is selected.
  return validated.length > 0 ? validated : [...DEFAULT_JURISDICTIONS];
}

function normalizeLanguages(languages: string[]): string[] {
  const validated = normalizeAndValidateValues("language", languages);
  // Ensure at least one language is selected.
  return validated.length > 0 ? validated : [...DEFAULT_LANGUAGES];
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

/**
 * True when constraints differ from `RESET_ALL`'s target state — anything the
 * user has set away from the `CH` / `de` defaults (jurisdictions, languages,
 * source type, official-only toggle, or any refinement). Kept colocated with
 * the `RESET_ALL` reducer so the two can't drift.
 */
export function hasActiveSearchConstraints(state: SearchConstraintsState): boolean {
  return countActiveSearchConstraints(state) > 0;
}

/**
 * How many constraints the user actually set — the count `RESET_ALL` would
 * clear.
 *
 * The seeded `CH` / `de` defaults are not user choices, so they are not
 * counted. The mobile filter badge used to count them, and so read "2" on a
 * cold load where the user had chosen nothing and the desktop panel said
 * "Keine Filter verfügbar" (#674). Same arithmetic as
 * `hasActiveSearchConstraints`, deliberately colocated so the badge, the reset
 * affordance, and the reset telemetry cannot disagree about what "active"
 * means.
 */
export function countActiveSearchConstraints(state: SearchConstraintsState): number {
  const { context, refinements } = state;
  const jurisdictionsChanged = context.jurisdictions.join(",") !== DEFAULT_JURISDICTIONS.join(",");
  const languagesChanged = context.languages.join(",") !== DEFAULT_LANGUAGES.join(",");

  return (
    (jurisdictionsChanged ? 1 : 0) +
    (languagesChanged ? 1 : 0) +
    (context.sourceType !== null ? 1 : 0) +
    (context.officialOnly ? 1 : 0) +
    refinements.length
  );
}

interface SearchConstraintsProviderProps {
  children: ReactNode;
}

export function SearchConstraintsProvider({ children }: SearchConstraintsProviderProps) {
  // Parsers come from `search-params.ts` — the `CH` / `de` defaults used to be
  // declared here as well as there, and the two copies disagreed: this file
  // defaulted to `["CH"]` / `["de"]` while `searchParamsParsers` gave both no
  // default at all (#822).
  const [urlState, setUrlState] = useQueryStates({
    jurisdictions: searchParamsParsers.jurisdictions,
    languages: searchParamsParsers.languages,
    sourceType: searchParamsParsers.sourceType,
    officialOnly: searchParamsParsers.officialOnly,
    refinements: searchParamsParsers.refinements,
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

  /**
   * Transient pre-reset snapshot used by `UNDO_RESET`. Stored in a ref —
   * not URL state — because undo is an ephemeral affordance tied to a
   * toast lifetime, not something that should survive navigation or be
   * shareable via a link.
   *
   * Invariant: the snapshot is cleared on any explicit user filter edit
   * so we never resurrect stale constraints after the user has moved on.
   */
  const lastSnapshotRef = useRef<SearchConstraintsState | null>(null);

  const captureSnapshot = useCallback(() => {
    lastSnapshotRef.current = state;
  }, [state]);

  const clearSnapshot = useCallback(() => {
    lastSnapshotRef.current = null;
  }, []);

  const dispatch = useMemo<Dispatch<SearchConstraintsAction>>(
    () => (action) => {
      switch (action.type) {
        case "TOGGLE_JURISDICTION":
          clearSnapshot();
          void setUrlState({
            jurisdictions: toggleValue(state.context.jurisdictions, action.jurisdiction),
          });
          break;

        case "TOGGLE_LANGUAGE":
          clearSnapshot();
          void setUrlState({
            languages: toggleValue(state.context.languages, action.language),
          });
          break;

        case "SET_SOURCE_TYPE":
          clearSnapshot();
          void setUrlState({ sourceType: action.sourceType });
          break;

        case "SET_OFFICIAL_ONLY":
          clearSnapshot();
          void setUrlState({ officialOnly: action.value });
          break;

        case "SET_REFINEMENT": {
          clearSnapshot();
          const existing = state.refinements.filter((r) => r.field !== action.field);
          void setUrlState({
            refinements: serializeRefinements([...existing, action.refinement]),
          });
          break;
        }

        case "CLEAR_REFINEMENT": {
          clearSnapshot();
          const next = state.refinements.filter((r) => r.field !== action.field);
          void setUrlState({
            refinements: next.length > 0 ? serializeRefinements(next) : null,
          });
          break;
        }

        case "CLEAR_ALL_REFINEMENTS":
          clearSnapshot();
          void setUrlState({ refinements: null });
          break;

        case "RESET_ALL":
          // Capture *before* the URL update so we can restore the exact
          // pre-reset constraints if the user hits "Undo".
          captureSnapshot();
          void setUrlState({
            jurisdictions: DEFAULT_JURISDICTIONS,
            languages: DEFAULT_LANGUAGES,
            sourceType: null,
            officialOnly: false,
            refinements: null,
          });
          break;

        case "UNDO_RESET": {
          const snapshot = lastSnapshotRef.current;
          if (!snapshot) break;
          lastSnapshotRef.current = null;
          void setUrlState({
            jurisdictions: snapshot.context.jurisdictions,
            languages: snapshot.context.languages,
            sourceType: snapshot.context.sourceType,
            officialOnly: snapshot.context.officialOnly,
            refinements:
              snapshot.refinements.length > 0 ? serializeRefinements(snapshot.refinements) : null,
          });
          break;
        }

        default:
          break;
      }
    },
    [setUrlState, state, captureSnapshot, clearSnapshot],
  );

  return (
    <SearchConstraintsContext.Provider value={{ state, dispatch }}>
      {children}
    </SearchConstraintsContext.Provider>
  );
}
