// React Query provider.
//
// React Query is the library that handles "fetch data, cache it, re-fetch
// when stale, track loading/error state." Every component that fetches data
// uses the hooks exposed by this library, and those hooks read a single
// shared cache -- which must be provided once near the top of the tree.
//
// This file exposes <QueryProvider> that we wrap around the whole app in
// src/app/layout.tsx. It is a *Client Component* (note the "use client"
// directive) because React Query relies on browser-only APIs.

"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

export function QueryProvider({ children }: { children: React.ReactNode }) {
  // useState ensures the QueryClient is created once per browser tab, not
  // on every re-render. Creating a new client every render would throw away
  // the cache.
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Don't spam the API while the user tabs between windows.
            refetchOnWindowFocus: false,
            // Re-fetch in the background after 30s; the cached value is
            // shown instantly while fresh data loads.
            staleTime: 30_000,
          },
        },
      }),
  );

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
