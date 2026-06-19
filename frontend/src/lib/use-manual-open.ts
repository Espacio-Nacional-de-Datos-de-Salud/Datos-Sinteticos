"use client";

// Shared open/closed state for the "Manual de instrucciones" panel.
//
// The manual is conceptually one book the user opens and closes while working:
// if they open it on one pipeline page it should stay open as they move to
// another, until they close it. Backing every page's panel with this single
// localStorage key gives that "same panel follows me" impression instead of an
// independent toggle per page.
//
// We deliberately do NOT use usePersistentState here. That hook starts from the
// default value and replays the stored value in an effect, so on every client
// navigation the new page mounts with the panel CLOSED for one frame before the
// effect flips it open — a visible flash. Instead we read localStorage
// synchronously via useSyncExternalStore: the client snapshot reflects the
// stored value on the very first render after a client navigation (no flash),
// while the separate server snapshot keeps the initial SSR hydration consistent
// (no mismatch warning).

import { useCallback, useSyncExternalStore } from "react";

const MANUAL_OPEN_KEY = "ends.ui.manualOpen";
// Same-document fan-out: the native `storage` event only fires in OTHER tabs,
// so we dispatch this to notify other subscribers in the current tab when the
// value changes (e.g. the page button and the rail's close button).
const MANUAL_OPEN_EVENT = "ends.ui.manualOpen.change";

function subscribe(onChange: () => void): () => void {
  window.addEventListener(MANUAL_OPEN_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(MANUAL_OPEN_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

function getSnapshot(): boolean {
  try {
    return window.localStorage.getItem(MANUAL_OPEN_KEY) === "true";
  } catch {
    return false;
  }
}

// Server snapshot — must be a stable value (closed) so SSR markup matches the
// first client render and React doesn't warn about a hydration mismatch.
function getServerSnapshot(): boolean {
  return false;
}

export function useManualOpen(): [boolean, (open: boolean) => void] {
  const open = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const setOpen = useCallback((next: boolean) => {
    try {
      window.localStorage.setItem(MANUAL_OPEN_KEY, next ? "true" : "false");
    } catch {
      /* ignore quota / unavailable storage */
    }
    // Notify other subscribers in this tab; useSyncExternalStore re-reads the
    // snapshot for every mounted consumer.
    window.dispatchEvent(new Event(MANUAL_OPEN_EVENT));
  }, []);

  return [open, setOpen];
}
