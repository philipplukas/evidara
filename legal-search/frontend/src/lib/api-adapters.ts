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

function mapSearchResultView(view: SearchResultView): SearchResultViewModel {
  return { ...view };
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
