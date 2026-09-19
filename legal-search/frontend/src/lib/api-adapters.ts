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
    // The headnote. The BFF already omits a blank one, but a whitespace-only
    // value must not reach the view either — `Regeste` renders nothing for it.
    regeste: detail.regeste,
    tabs: detail.tabs,
    relatedGroups: detail.relatedGroups.map((group) => ({
      groupLabel: group.label,
      items: group.items,
    })),
    // Reference rows are carried field by field rather than passed through,
    // so a key the API stops sending fails the typecheck here instead of
    // rendering as nothing. The passthrough is how `subtitle` — a key no
    // response ever carried — survived in `ReferenceItem` while the real
    // `citation` went unrendered (#1040).
    references: detail.references.map((group) => ({
      direction: group.label,
      items: group.items.map((item) => ({
        id: item.id,
        title: item.title,
        citation: item.citation,
        href: item.href,
        targetDocumentId: item.targetDocumentId,
        resolved: item.resolved,
        unresolvedReason: item.unresolvedReason,
      })),
    })),
    annotations: detail.annotations.map((annotation) => ({
      title: annotation.label,
      content: annotation.text,
    })),
    // `depth` and `text` are the second half of #1040's dropped structure: the
    // BFF sends both and this mapper kept only `{id, label, active}`, which is
    // why the outline rendered flat and textless however deep the document
    // was. Same defect shape as #609 — a field carried all the way to the
    // adapter and left behind in it.
    localStructure: detail.localStructure?.items
      ? {
          items: detail.localStructure.items.map((item) => ({
            id: item.id,
            label: item.label,
            active: item.active ?? false,
            depth: item.depth,
            text: item.text,
          })),
        }
      : undefined,
    contentLanguage: detail.contentLanguage,
  };
}
