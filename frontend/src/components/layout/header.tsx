"use client";

import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { MoreVertical, Trash2, Zap } from "lucide-react";
import { toast } from "sonner";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { killBgProcesses, purgeAll } from "@/lib/api";

export function Header() {
  const [isKillingBg, setIsKillingBg] = useState(false);
  const [isPurgingAll, setIsPurgingAll] = useState(false);
  const [confirmPurgeAll, setConfirmPurgeAll] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close the overflow menu on outside-click / Escape.
  useEffect(() => {
    if (!menuOpen) return;
    const onClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  const handleKillBg = useCallback(async () => {
    setMenuOpen(false);
    setIsKillingBg(true);
    try {
      const result = await killBgProcesses();
      const parts: string[] = [];
      if (result.killed_pids.length > 0)
        parts.push(`${result.killed_pids.length} proceso(s) eliminado(s)`);
      if (result.cancelled_simulations.length > 0)
        parts.push(`${result.cancelled_simulations.length} simulación(es) cancelada(s)`);
      toast.success(parts.length > 0 ? parts.join(" · ") : "Nada que limpiar");
    } catch {
      toast.error("Error al limpiar procesos en segundo plano");
    } finally {
      setIsKillingBg(false);
    }
  }, []);

  const handlePurgeAll = useCallback(async () => {
    setIsPurgingAll(true);
    try {
      const result = await purgeAll();
      const total =
        result.inspections.length +
        result.configs_removed.length +
        result.configs_created.length +
        result.models.length +
        result.simulations.length +
        result.evaluations.length;
      toast.success(
        total > 0
          ? `${total} artefacto(s) eliminado(s) — programa reiniciado a cero`
          : "No había nada que eliminar",
      );
    } catch {
      toast.error("Error al eliminar todos los artefactos");
    } finally {
      setIsPurgingAll(false);
    }
  }, []);

  return (
    <header className="flex h-14 shrink-0 items-center justify-between bg-[#00215C] px-6 shadow-[0_2px_8px_rgba(0,0,0,0.2)]">
      <Link href="/" aria-label="Inicio" className="flex items-center gap-3.5">
        <Image
          src="/ends-assets/END_LOGO_BLANCO.svg"
          alt="Espacio Nacional de Datos de Salud"
          width={140}
          height={28}
          priority
          className="h-7 w-auto"
        />
        <span className="h-7 w-px bg-white/20" />
        <span className="text-[13px] font-semibold tracking-wide text-white/85">
          Datos Sintéticos
        </span>
        <span className="h-[3px] w-6 rounded-sm bg-[#FFDB00]" />
      </Link>

      <div className="flex items-center gap-3.5">
        <div ref={menuRef} className="relative">
          <button
            type="button"
            aria-label="Herramientas de mantenimiento"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((v) => !v)}
            className="flex h-8 w-8 items-center justify-center rounded text-white/70 transition-colors hover:bg-white/10 hover:text-white"
          >
            <MoreVertical className="h-4 w-4" />
          </button>
          {menuOpen && (
            <div
              role="menu"
              className="absolute right-0 top-full z-50 mt-1 w-60 overflow-hidden rounded-md border border-border bg-popover py-1 text-popover-foreground shadow-md"
            >
              <button
                type="button"
                role="menuitem"
                disabled={isKillingBg}
                onClick={handleKillBg}
                title="Elimina todos los procesos corriendo en segundo plano, limpiando procesos colgados. No afecta al servidor ni al frontend."
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors hover:bg-muted disabled:pointer-events-none disabled:opacity-50"
              >
                <Zap className="h-4 w-4 shrink-0 text-muted-foreground" />
                {isKillingBg ? "Limpiando…" : "Panic Button"}
              </button>
              <button
                type="button"
                role="menuitem"
                disabled={isPurgingAll}
                onClick={() => {
                  setMenuOpen(false);
                  setConfirmPurgeAll(true);
                }}
                title="Elimina TODO: cargas de datos, reglas, modelos, generaciones y evaluaciones, y reinicia la configuración. Deja el programa a cero. Úsalo con cuidado."
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-destructive transition-colors hover:bg-destructive/10 disabled:pointer-events-none disabled:opacity-50"
              >
                <Trash2 className="h-4 w-4 shrink-0" />
                {isPurgingAll ? "Eliminando…" : "Borrar todo"}
              </button>
            </div>
          )}
        </div>
        <ThemeToggle />
      </div>
      <ConfirmDialog
        open={confirmPurgeAll}
        title="¿Borrar todo el programa?"
        description="Se eliminarán TODAS las cargas de datos, reglas de negocio, modelos, generaciones y evaluaciones, y se reiniciará la configuración a sus valores por defecto. El programa quedará a cero. Esta acción no se puede deshacer."
        confirmLabel="Borrar todo"
        onConfirm={() => {
          setConfirmPurgeAll(false);
          void handlePurgeAll();
        }}
        onCancel={() => setConfirmPurgeAll(false)}
      />
    </header>
  );
}
