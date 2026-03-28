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

export interface MetadataRow {
  label: string;
  value: string;
  iconKey?: string;
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
  contentHtml?: string;
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
