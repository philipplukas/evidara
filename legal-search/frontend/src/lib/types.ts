// ─── BFF ViewModel Contracts ───
// The frontend renders these; the BFF decides what goes in them.

export interface ContentLanguage {
  display: string;
  original: string;
  isTranslation: boolean;
  label?: string;
}

export interface BadgeViewModel {
  label: string;
  colorKey: string;
  iconKey?: string;
}

export type MetadataVisibility = "always" | "default" | "expanded";
export type MetadataDensity = "compact" | "default" | "expanded";

export interface MetadataRow {
  label: string;
  value: string;
  iconKey?: string;
  /** When set by the BFF, overrides client-side `metadata-visibility` heuristics. */
  visibility?: MetadataVisibility;
}

export interface MetadataField extends MetadataRow {
  visibility: MetadataVisibility;
}

export interface RelatedCount {
  label: string;
  count: number;
  href?: string;
}

export interface ActionViewModel {
  label: string;
  icon: string;
  href?: string;
}

export interface SearchResultViewModel {
  id: string;
  type: string;
  title: string;
  subtitle: string;
  snippet: string;
  structuralContext?: string;
  badges: BadgeViewModel[];
  metadataRows: MetadataRow[];
  relatedCounts: RelatedCount[];
  actions: ActionViewModel[];
  contentLanguage?: ContentLanguage;
  /**
   * Discriminator from the search projection (PR #441). Drives the
   * commentary-vs-document card variant — `commentary_insight` rows
   * render via `CommentaryResultCard`. `legal_document` and
   * `undefined` route to the default `ResultCard`.
   *
   * Note: the BFF emits this field on `SearchResultView`; the orval-
   * generated client may not pick it up until the OpenAPI spec is
   * bumped. The fallback discriminator is `type === "commentary"`.
   */
  recordKind?: "legal_document" | "commentary_insight";
  /**
   * Canonical primary documents this commentary references. Rendered
   * as source-document links on commentary cards. Empty / undefined
   * for legal_document rows.
   */
  sourceDocumentIds?: string[];
}

export interface RelatedItem {
  id: string;
  title: string;
  subtitle?: string;
  badge?: BadgeViewModel;
  href?: string;
}

export interface ReferenceItem {
  id: string;
  title: string;
  subtitle?: string;
  href?: string;
}

export interface AnnotationViewModel {
  title: string;
  content: string;
  provenance?: string;
  sourceCount?: number;
  confidence?: string;
}

export interface TabViewModel {
  key: string;
  label: string;
  count?: number;
}

export interface RelatedGroup {
  groupLabel: string;
  items: RelatedItem[];
}

export interface ReferenceGroup {
  direction: string;
  items: ReferenceItem[];
}

export interface LocalStructureItem {
  id: string;
  label: string;
  active: boolean;
}

export interface DetailViewModel {
  id: string;
  type: string;
  title: string;
  subtitle: string;
  breadcrumbs: string[];
  metadata: MetadataRow[];
  /**
   * The document body as plain text, straight from `DetailView.content`.
   * Paragraphs are separated by blank lines; there is no markup. This replaced
   * `contentHtml`, which no API response ever populated — only `mock-data.ts`
   * did, which is why the body's absence in production went unnoticed (#609).
   */
  contentText?: string;
  contentLanguage?: ContentLanguage;
  tabs: TabViewModel[];
  relatedGroups: RelatedGroup[];
  references: ReferenceGroup[];
  annotations: AnnotationViewModel[];
  localStructure?: { items: LocalStructureItem[] };
}

export interface FilterOption {
  value: string;
  label: string;
  count?: number;
  iconKey?: string;
}

export interface FilterViewModel {
  key: string;
  label: string;
  type: "checkbox" | "chip" | "dropdown" | "date" | "toggle";
  options: FilterOption[];
  selected: string[];
}

export interface ContextChip {
  key: string;
  label: string;
  active: boolean;
  iconKey?: string;
}

export interface SearchContextViewModel {
  jurisdictions: ContextChip[];
  languages: ContextChip[];
  sourceTypes: ContextChip[];
  exactMatches?: SearchResultViewModel[];
}

// ─── Workspace Interaction Model ───

export type ResultSetSource =
  | { type: "search"; query: string }
  | { type: "pivot"; label: string; parentSource: ResultSetSource };

export interface TrailEntry {
  id: string;
  title: string;
  type: string;
  timestamp: number;
}

export interface PinnedItem {
  id: string;
  title: string;
  type: string;
}

export interface ResultSet {
  source: ResultSetSource;
  items: SearchResultViewModel[];
  scopeLabel: string;
  /**
   * Total hits the search matched, which `items` is one page of. Optional
   * because pivots and boot paths may not carry it; consumers fall back to
   * `items.length`. Never derive the count from `items` when this is present —
   * that is #615.
   */
  totalResults?: number;
}

// ─── Search Constraints (ES-ready shapes) ───

/** High-level context: jurisdictions, languages, source type */
export interface ContextConstraints {
  jurisdictions: string[];
  languages: string[];
  sourceType: string | null;
  officialOnly: boolean;
}

/**
 * A single refinement filter, shaped to map cleanly to ES query DSL.
 *
 * - "terms"      → ES terms aggregation (court, document type)
 * - "date_range" → ES date_range aggregation
 * - "range"      → ES range query (numeric)
 * - "toggle"     → ES term query (boolean field)
 * - "text"       → ES match query (full-text sub-filter)
 */
export interface SearchRefinement {
  field: string;
  type: "terms" | "date_range" | "range" | "toggle" | "text";
  values: string[];
  from?: string;
  to?: string;
  value?: boolean | string;
}

export interface SearchConstraintsState {
  context: ContextConstraints;
  refinements: SearchRefinement[];
}
