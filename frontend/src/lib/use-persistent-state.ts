"use client";

// SSR-safe localStorage-backed state. The first render returns `defaultValue`
// so the server and client markup agree (avoiding a hydration mismatch); the
// stored value is replayed on mount. Mirrors the hydration approach used by
// useUpstreamSelection. Every update writes through to localStorage so the
// value survives reloads and is shared across pages that use the same key.

import { useCallback, useEffect, useState } from "react";

export function usePersistentState<T>(
  storageKey: string,
  defaultValue: T,
): [T, (value: T | ((prev: T) => T)) => void] {
  const [value, setValue] = useState<T>(defaultValue);

  useEffect(() => {
    const stored = window.localStorage.getItem(storageKey);
    if (stored != null) {
      try {
        setValue(JSON.parse(stored) as T); // eslint-disable-line react-hooks/set-state-in-effect
      } catch {
        /* ignore a corrupt stored value and keep the default */
      }
    }
  }, [storageKey]);

  const set = useCallback(
    (next: T | ((prev: T) => T)) => {
      setValue((prev) => {
        const resolved =
          typeof next === "function" ? (next as (p: T) => T)(prev) : next;
        try {
          window.localStorage.setItem(storageKey, JSON.stringify(resolved));
        } catch {
          /* ignore quota / unavailable storage */
        }
        return resolved;
      });
    },
    [storageKey],
  );

  return [value, set];
}
