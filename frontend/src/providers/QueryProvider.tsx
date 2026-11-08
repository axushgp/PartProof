"use client";

import { ReactNode, useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

export function QueryProvider({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 5000,
            retry: (failureCount, error) => {
              // Do not retry 401 or 404
              if (
                error &&
                typeof error === "object" &&
                "status" in error &&
                [401, 403, 404].includes((error as { status: number }).status)
              ) {
                return false;
              }
              return failureCount < 1;
            },
            refetchOnWindowFocus: true,
          },
        },
      })
  );

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
