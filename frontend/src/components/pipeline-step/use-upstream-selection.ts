"use client";

// Pattern shared by the wizard-step pages: each step picks one
// upstream-completed artifact (inspection for Entrenamiento, model for
// Generación, simulation for Auditoría). The same three rules apply
// everywhere:
//   1. Hydrate the last-used selection from localStorage on mount.
//   2. If the stored id is missing or no longer points at a completed
//      artifact, fall back to the most recent completed one.
//   3. Otherwise keep the user's explicit choice.

import { useCallback, useEffect, useRef, useState } from "react";

export function useUpstreamSelection<T>(
  items: T[],
  idField: keyof T & string,
  storageKey: string,
): {
  selectedId: string;
  setSelectedId: (id: string) => void;
  hydrated: boolean;
} {
  const [selectedId, setSelectedIdState] = useState<string>("");
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    // Mount-time hydration: SSR and the first client render must agree on
    // "" so React doesn't bail out of hydration; we replay from localStorage
    // on the client right after.
    const stored = window.localStorage.getItem(storageKey);
    if (stored) setSelectedIdState(stored); // eslint-disable-line react-hooks/set-state-in-effect
    setHydrated(true);
  }, [storageKey]);

  // Persisting wrapper: callers (and the default-pick effect below) write
  // through to localStorage so a newly selected upstream artefact survives
  // a reload. Without this, the stored value drifts from the in-memory
  // selection and `useUpstreamSelection` snaps back to the old id on mount.
  const setSelectedId = useCallback(
    (id: string) => {
      if (id) window.localStorage.setItem(storageKey, id);
      else window.localStorage.removeItem(storageKey);
      setSelectedIdState(id);
    },
    [storageKey],
  );

  // Default-pick: fall back to the first item only ONCE — on initial load,
  // when nothing valid was hydrated from localStorage. Re-running on every
  // items change would race against optimistic selections: a caller that
  // `setSelectedId(newId)` then invalidates the list query would see the
  // selection snap back to items[0] in the brief window before the new id
  // appears in the refetched list.
  const settledOnce = useRef(false);
  useEffect(() => {
    if (settledOnce.current || !hydrated || items.length === 0) return;
    if (selectedId && items.some((item) => item[idField] === selectedId)) {
      settledOnce.current = true;
      return;
    }
    setSelectedId(String(items[0][idField])); // eslint-disable-line react-hooks/set-state-in-effect
    settledOnce.current = true;
  }, [hydrated, items, idField, selectedId, setSelectedId]);

  return { selectedId, setSelectedId, hydrated };
}
