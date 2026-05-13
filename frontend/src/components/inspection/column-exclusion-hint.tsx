"use client";

import { Info } from "lucide-react";

// Small badge with a hover/focus tooltip that explains how column exclusion
// works. Used in two places — the types card (immediate × button) and the
// selection-preview card (deferred at run launch) — with a slightly different
// copy for each.
export function ColumnExclusionHint({
  compact = false,
  immediate = false,
  align = "left",
}: {
  compact?: boolean;
  immediate?: boolean;
  align?: "left" | "right";
}) {
  const tooltipPosition =
    align === "right" ? "right-0 left-auto" : "left-0";

  return (
    <span
      className="group relative inline-flex items-center gap-1 align-middle focus-visible:outline-none"
      tabIndex={0}
    >
      <span className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-300">
        <Info className="h-3 w-3" aria-hidden="true" />
        {compact ? "Exclusión" : "Excluir columnas"}
      </span>
      <span
        className={`pointer-events-none absolute top-full z-20 mt-1 hidden w-72 max-w-[min(18rem,calc(100vw-2rem))] rounded-md border bg-popover px-3 py-2 text-left text-xs font-normal leading-relaxed text-popover-foreground shadow-md group-hover:block group-focus-within:block ${tooltipPosition}`}
      >
        {immediate
          ? "El botón × excluye la columna de inmediato del esquema y de los datos preprocesados. No se revierte con Restaurar autodetectado."
          : "Elimina columnas haciendo clic en su nombre en la lista que aparece al desplegar la muestra. Al iniciar, las excluidas quedan fuera del esquema y de los datos preprocesados."}
        {" "}En evaluación, las métricas comparan sólo las columnas comunes entre
        datos reales y sintéticos.
      </span>
    </span>
  );
}
