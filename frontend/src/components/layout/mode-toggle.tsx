"use client";

// Production / Dev mode switch shown in the header.
//
// Renders as a two-segment pill so the current mode is always obvious — a
// plain icon button leaves users wondering what state they're in. In dev
// mode we surface the Pipelines authoring tools in the sidebar.

import { Wrench, ShieldCheck } from "lucide-react";
import { useMode } from "@/lib/mode";
import { cn } from "@/lib/utils";

export function ModeToggle() {
  const { mode, setMode, ready } = useMode();

  const isDev = ready && mode === "dev";

  const segment =
    "flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold transition-colors";
  const active = "bg-[#FFDB00] text-[#00215C]";
  const idle = "text-white/70 hover:text-white";

  return (
    <div
      role="group"
      aria-label="Modo de aplicación"
      className="flex items-center gap-1 rounded-full border border-white/20 bg-white/10 p-0.5"
    >
      <button
        type="button"
        aria-pressed={!isDev}
        onClick={() => setMode("production")}
        className={cn(segment, !isDev ? active : idle)}
        title="Modo producción: solo el flujo estándar"
      >
        <ShieldCheck className="h-3 w-3" />
        <span>Producción</span>
      </button>
      <button
        type="button"
        aria-pressed={isDev}
        onClick={() => setMode("dev")}
        className={cn(segment, isDev ? active : idle)}
        title="Modo desarrollo: habilita el editor de pipelines"
      >
        <Wrench className="h-3 w-3" />
        <span>Dev</span>
      </button>
    </div>
  );
}
