"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { NuqsAdapter } from "nuqs/adapters/next/app";
import type { ReactNode } from "react";
import { queryClient } from "@/lib/query-client";

/**
 * Wraps application content with required context providers.
 *
 * Renders an outer NuqsAdapter, supplies React Query context to `children`, and includes the React Query devtools (initially closed).
 *
 * @param children - The React nodes to render inside the providers
 * @returns The provider-wrapped React element containing `children`
 */
export function Providers({ children }: { children: ReactNode }) {
  return (
    <NuqsAdapter>
      <QueryClientProvider client={queryClient}>
        {children}
        <ReactQueryDevtools initialIsOpen={false} />
      </QueryClientProvider>
    </NuqsAdapter>
  );
}
