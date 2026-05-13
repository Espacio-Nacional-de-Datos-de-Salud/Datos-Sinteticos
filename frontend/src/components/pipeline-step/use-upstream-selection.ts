"use client";

// Pattern shared by the wizard-step pages: each step picks one
// upstream-completed artifact (inspection for Entrenamiento, model for
// Generación, simulation for Auditoría). The same three rules apply
// everywhere:
//   1. Hydrate the last-used selection from localStorage on mount.
//   2. If the stored id is missing or no longer points at a completed
//      artifact, fall back to the most recent completed one.
//   3. Otherwise keep the user's explicit choice.

import { useEffect, useState } from "react";

export function useUpstreamSelection<T>(
  items: T[],
  idField: keyof T & string,
  storageKey: string,
): {
  selectedId: string;
  setSelectedId: (id: string) => void;
  hydrated: boolean;
} {
  const [selectedId, setSelectedId] = useState<string>("");
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    // Mount-time hydration: SSR and the first client render must agree on
    // "" so React doesn't bail out of hydration; we replay from localStorage
    // on the client right after.
    const stored = window.localStorage.getItem(storageKey);
    if (stored) setSelectedId(stored); // eslint-disable-line react-hooks/set-state-in-effect
    setHydrated(true);
  }, [storageKey]);

  // Default to the first completed item once items load, unless the user's
  // existing selection is still valid. Rerunning when items change is
  // intentional — a hidden completed → not-completed transition (e.g. delete)
  // should also bump the selection forward.
  useEffect(() => {
    if (!hydrated || items.length === 0) return;
    if (selectedId && items.some((item) => item[idField] === selectedId)) {
      return;
    }
    setSelectedId(String(items[0][idField])); // eslint-disable-line react-hooks/set-state-in-effect
  }, [hydrated, items, idField, selectedId]);

  return { selectedId, setSelectedId, hydrated };
}
