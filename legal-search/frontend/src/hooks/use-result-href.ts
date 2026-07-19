"use client";

import { useSearchParams } from "next/navigation";
import { useCallback } from "react";
import { buildResultHref } from "@/lib/result-href";

/**
 * Returns a builder for result deep links that keeps the current query string
 * (`q`, active constraints, …) and swaps in the `item` parameter.
 *
 * Kept as a hook because `useSearchParams` is the only reliable source of the
 * current URL during client rendering; the interesting logic lives in the pure
 * `buildResultHref` so it can be unit-tested without a router.
 */
export function useResultHrefBuilder(): (resultId: string) => string {
  const searchParams = useSearchParams();
  const search = searchParams?.toString() ?? "";
  return useCallback((resultId: string) => buildResultHref(search, resultId), [search]);
}
