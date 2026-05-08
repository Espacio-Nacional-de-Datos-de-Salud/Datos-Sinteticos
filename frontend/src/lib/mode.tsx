// App-mode toggle: "production" vs "dev".
//
// Production is the default — operators see only the four pipeline steps and
// the home dashboard. Dev mode unlocks the Pipelines authoring/runner page
// (and any other forthcoming engineering tooling).
//
// State is persisted in localStorage so the choice survives page reloads,
// but it is NOT a security boundary — the backend exposes the same routes
// regardless. Dev mode just hides UI from non-technical users by default.

"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

export type AppMode = "production" | "dev";

const STORAGE_KEY = "ends.appMode";
const DEFAULT_MODE: AppMode = "production";

type ModeContextValue = {
  mode: AppMode;
  setMode: (m: AppMode) => void;
  toggleMode: () => void;
  /** True once we've read localStorage; before that, render production-safe defaults. */
  ready: boolean;
};

const ModeContext = createContext<ModeContextValue | null>(null);

export function ModeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<AppMode>(DEFAULT_MODE);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored === "dev" || stored === "production") {
        setModeState(stored);
      }
    } catch {
      // localStorage may be unavailable (SSR/private mode); fall back to default.
    }
    setReady(true);
  }, []);

  const setMode = useCallback((next: AppMode) => {
    setModeState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // ignore — non-persistence is acceptable.
    }
  }, []);

  const toggleMode = useCallback(() => {
    setMode(mode === "dev" ? "production" : "dev");
  }, [mode, setMode]);

  return (
    <ModeContext.Provider value={{ mode, setMode, toggleMode, ready }}>
      {children}
    </ModeContext.Provider>
  );
}

export function useMode(): ModeContextValue {
  const ctx = useContext(ModeContext);
  if (!ctx) throw new Error("useMode must be used inside <ModeProvider>");
  return ctx;
}

/** Convenience hook: true when dev-only UI should render. */
export function useIsDev(): boolean {
  const { mode, ready } = useMode();
  return ready && mode === "dev";
}
