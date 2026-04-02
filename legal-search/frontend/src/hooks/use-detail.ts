import { useQuery } from "@tanstack/react-query";
import type { DetailViewModel } from "@/lib/types";

/**
 * Fetches detail data for a given item ID.
 *
 * Phase 1: synchronous mock lookup (matches current behavior).
 * Phase 2: swap fetchDetail to async BFF fetch.
 */
export function useDetail(id: string | null) {
  return useQuery<DetailViewModel | null>({
    queryKey: ["detail", id],
    queryFn: () => fetchDetail(id!),
    enabled: id !== null,
  });
}

// Phase 1: mock adapter — returns static data from mock-data module
async function fetchDetail(id: string): Promise<DetailViewModel | null> {
  const { articleDetail, decisionDetail } = await import("@/lib/mock-data");
  const detailMap: Record<string, DetailViewModel> = {
    "law-1": articleDetail,
    "decision-1": decisionDetail,
  };
  return detailMap[id] ?? null;
}
