import type {
  DetailView,
  FilterFacetView,
  SearchContextView,
  SearchResponseView,
  SearchResultView,
} from "@/lib/api/generated/model";
import type {
  DetailViewModel,
  FilterViewModel,
  RecordKind,
  SearchContextViewModel,
  SearchResultViewModel,
} from "@/lib/types";

function mapFacetsToFilters(facets: FilterFacetView[]): FilterViewModel[] {
  return facets.map((facet) => ({
    key: facet.key,
    label: facet.label,
    type: facet.type,
    options: facet.options,
    selected: [],
  }));
}

/**
 * Pulls commentary metadata off a generated `SearchResultView`. The
 * generated client may lag the BFF (the OpenAPI spec is regenerated
 * separately), so we read these fields defensively at runtime and
 * forward them onto the `SearchResultViewModel` without throwing if
 * the spec hasn't caught up yet.
 *
 * Tracked by #425 (BFF) / #431 (frontend rendering).
 */
function readCommentaryFields(view: SearchResultView): {
  recordKind?: RecordKind;
  sourceDocumentIds?: string[];
  commentarySupportCount?: number;
} {
  const extra = view as SearchResultView & {
    recordKind?: RecordKind;
    sourceDocumentIds?: string[];
    commentarySupportCount?: number;
  };

  return {
    recordKind: extra.recordKind,
    sourceDocumentIds: Array.isArray(extra.sourceDocumentIds) ? extra.sourceDocumentIds : undefined,
    commentarySupportCount:
      typeof extra.commentarySupportCount === "number" && extra.commentarySupportCount >= 0
        ? extra.commentarySupportCount
        : undefined,
  };
}

function mapSearchResultView(view: SearchResultView): SearchResultViewModel {
  const commentary = readCommentaryFields(view);
  return {
    ...view,
    ...commentary,
  };
}

export function mapSearchResponse(response: SearchResponseView): {
  results: SearchResultViewModel[];
  filters: FilterViewModel[];
} {
  return {
    results: response.results.map(mapSearchResultView),
    filters: mapFacetsToFilters(response.facets),
  };
}

export function mapSearchContext(context: SearchContextView): SearchContextViewModel {
  return {
    jurisdictions: context.jurisdictions,
    languages: context.languages,
    sourceTypes: context.sourceTypes,
    exactMatches: context.exactMatches?.map(mapSearchResultView),
  };
}

export function mapDetail(detail: DetailView): DetailViewModel {
  return {
    id: detail.id,
    type: detail.type,
    title: detail.title,
    subtitle: detail.subtitle,
    breadcrumbs: detail.breadcrumbs ?? [],
    metadata: detail.metadata,
    tabs: detail.tabs,
    relatedGroups: detail.relatedGroups.map((group) => ({
      groupLabel: group.label,
      items: group.items,
    })),
    references: detail.references.map((group) => ({
      direction: group.label,
      items: group.items,
    })),
    annotations: detail.annotations.map((annotation) => ({
      title: annotation.label,
      content: annotation.text,
    })),
    localStructure: detail.localStructure?.items
      ? {
          items: detail.localStructure.items.map((item) => ({
            id: item.id,
            label: item.label,
            active: item.active ?? false,
          })),
        }
      : undefined,
    contentLanguage: detail.contentLanguage,
  };
}
