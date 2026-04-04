"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { NuqsAdapter } from "nuqs/adapters/next/app";
import type { ReactNode } from "react";
import { LocaleProvider } from "@/lib/locale-context";
import { queryClient } from "@/lib/query-client";

/**
 * Wraps application content with required context providers.
 *
 * Renders an outer NuqsAdapter, supplies locale context and React Query
 * context to `children`, and includes the React Query devtools.
 */
export function Providers({ children }: { children: ReactNode }) {
  return (
    <NuqsAdapter>
      <LocaleProvider>
        <QueryClientProvider client={queryClient}>
          {children}
          <ReactQueryDevtools initialIsOpen={false} />
        </QueryClientProvider>
      </LocaleProvider>
    </NuqsAdapter>
  );
}
