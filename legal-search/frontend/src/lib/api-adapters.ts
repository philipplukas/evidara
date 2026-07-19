import type {
  DetailView,
  FilterFacetView,
  SearchContextView,
  SearchResponseView,
} from "@/lib/api/generated/model";
import type { DetailViewModel, FilterViewModel, SearchContextViewModel } from "@/lib/types";

function mapFacetsToFilters(facets: FilterFacetView[]): FilterViewModel[] {
  return facets.map((facet) => ({
    key: facet.key,
    label: facet.label,
    type: facet.type,
    options: facet.options,
    selected: [],
  }));
}

export function mapSearchResponse(response: SearchResponseView): {
  results: SearchResponseView["results"];
  filters: FilterViewModel[];
  totalResults: number;
} {
  return {
    results: response.results,
    filters: mapFacetsToFilters(response.facets),
    // The hit count, not the page. `results` is one page of `totalResults`, so
    // counting the array reports "20 Ergebnisse" for a 25-hit search. Telling a
    // legal researcher a search found fewer documents than it did is a
    // correctness problem, not a cosmetic one (#615).
    totalResults: response.totalResults,
  };
}

export function mapSearchContext(context: SearchContextView): SearchContextViewModel {
  return {
    jurisdictions: context.jurisdictions,
    languages: context.languages,
    sourceTypes: context.sourceTypes,
    exactMatches: context.exactMatches,
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
    // The body. This mapping is the whole of #609: every other field was
    // carried across and `content` alone was left behind, so the API could
    // return a full document text and the view would never see it.
    contentText: detail.content,
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
