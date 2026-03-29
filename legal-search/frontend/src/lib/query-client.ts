import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5min: legal data doesn't change often
      gcTime: 30 * 60 * 1000, // 30min cache lifetime
      refetchOnWindowFocus: false, // don't refetch legal data on tab switch
    },
  },
});
