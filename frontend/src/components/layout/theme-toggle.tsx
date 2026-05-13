"use client";

import { useEffect, useState } from "react";
import { useTheme } from "next-themes";
import { Moon, Sun } from "lucide-react";

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const isDark = mounted && resolvedTheme === "dark";
  const next = isDark ? "light" : "dark";

  return (
    <button
      type="button"
      aria-label={mounted ? `Cambiar a tema ${next === "dark" ? "oscuro" : "claro"}` : "Cambiar tema"}
      onClick={() => setTheme(next)}
      className="flex h-9 w-9 items-center justify-center rounded-full border border-border bg-secondary text-secondary-foreground transition-all hover:scale-105 hover:bg-secondary/85 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      {mounted ? (
        isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />
      ) : (
        <Moon className="h-4 w-4" />
      )}
    </button>
  );
}
