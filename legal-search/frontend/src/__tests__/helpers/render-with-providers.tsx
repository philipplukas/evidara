import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type RenderOptions, render } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import type { ReactElement, ReactNode } from "react";
import { MESSAGES } from "@/i18n/messages";
import { searchResults } from "@/lib/mock-data";
import { SearchConstraintsProvider } from "@/lib/search-constraints-store";
import type { SearchResultViewModel } from "@/lib/types";
import { WorkspaceProvider } from "@/lib/workspace-store";

interface ProviderOptions {
  initialQuery?: string;
  initialResults?: SearchResultViewModel[];
  /** Total hits the search matched, which `initialResults` is one page of. */
  initialTotalResults?: number;
  /** URL search params to initialize nuqs with, e.g. { item: "law-1", tab: "related" } */
  searchParams?: Record<string, string>;
}

/**
 * Wraps a component in all required providers for testing:
 * - NuqsTestingAdapter (URL state)
 * - QueryClientProvider (React Query)
 * - WorkspaceProvider (workspace state)
 * - SearchConstraintsProvider (filter state)
 */
export function renderWithProviders(
  ui: ReactElement,
  options?: ProviderOptions & Omit<RenderOptions, "wrapper">,
) {
  const {
    initialQuery = "Art 754 OR",
    initialResults = searchResults,
    initialTotalResults,
    searchParams = {},
    ...renderOptions
  } = options ?? {};

  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <NuqsTestingAdapter searchParams={searchParams}>
        <QueryClientProvider client={queryClient}>
          <NextIntlClientProvider locale="de" messages={MESSAGES.de}>
            <SearchConstraintsProvider>
              <WorkspaceProvider
                initialResults={initialResults}
                initialQuery={initialQuery}
                initialTotalResults={initialTotalResults}
              >
                {children}
              </WorkspaceProvider>
            </SearchConstraintsProvider>
          </NextIntlClientProvider>
        </QueryClientProvider>
      </NuqsTestingAdapter>
    );
  }

  return render(ui, { wrapper: Wrapper, ...renderOptions });
}
