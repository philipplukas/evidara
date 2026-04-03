import { useQuery } from "@tanstack/react-query";
import { getDocument } from "@/lib/api/generated/client";
import { mapDetail } from "@/lib/api-adapters";
import type { DetailViewModel } from "@/lib/types";

export function useDetail(id: string | null) {
  return useQuery<DetailViewModel | null>({
    queryKey: ["detail", id],
    queryFn: () => fetchDetail(id!),
    enabled: id !== null,
  });
}

async function fetchDetail(id: string): Promise<DetailViewModel | null> {
  const response = await getDocument(id);
  if (response.status === 404) {
    return null;
  }
  if (response.status !== 200) {
    throw new Error("Failed to load document detail.");
  }
  return mapDetail(response.data);
}
