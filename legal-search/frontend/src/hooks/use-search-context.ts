"use client";

import { useQuery } from "@tanstack/react-query";
import { getSearchContext } from "@/lib/api/generated/client";
import { mapSearchContext } from "@/lib/api-adapters";

export function useSearchContext() {
  return useQuery({
    queryKey: ["search-context"],
    queryFn: async () => {
      const response = await getSearchContext();
      if (response.status !== 200) {
        throw new Error("Failed to load search context.");
      }
      return mapSearchContext(response.data);
    },
  });
}
