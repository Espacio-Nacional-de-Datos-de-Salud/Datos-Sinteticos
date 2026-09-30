"use client";

import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { RotateCcw, Trash2 } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { CollapseToggle } from "@/components/ui/collapse-toggle";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type Autodetect } from "@/lib/api";

// Reglas-de-negocio (BRC) column exclusion. The toggle is non-destructive: it
// only updates the inspection metadata's *separate* `rules_excluded_columns`
// field — never `excluded_columns` (the Carga de Datos list) — so a drop chosen
// here does not bleed back into Carga de Datos. The cached parquet keeps the
// column so BRC can still reference it from logical / derived rules — the column
// is dropped at the end of each *new* BRC run, before persisting, so downstream
// consumers (training, generation, audit) never see it. Existing BRC runs are
// not rewritten.
export function ColumnDeletionCard({
  inspectionId,
  autodetect,
  isLoading,
  isError,
  defaultOpen = true,
}: {
  inspectionId: string | null;
  autodetect: Autodetect | undefined;
  isLoading: boolean;
  isError: boolean;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const tables = useMemo(
    () => Object.entries(autodetect?.encoding_types ?? {}),
    [autodetect?.encoding_types],
  );

  const excludedByTable = autodetect?.rules_excluded_columns ?? {};

  const mutation = useMutation({
    mutationFn: async (next: Record<string, string[]>) => {
      if (!inspectionId) throw new Error("Sin inspección activa");
      const { data } = await api.put<Autodetect>(
        `/inspections/${inspectionId}/autodetect/rules-exclusions`,
        { excluded_columns: next },
      );
      return data;
    },
    onSuccess: (data) => {
      queryClient.setQueryData(["autodetect", inspectionId], data);
      setPendingKey(null);
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Error desconocido";
      toast.error(`No se pudo actualizar la exclusión: ${msg}`);
      setPendingKey(null);
    },
  });

  const toggle = (table: string, col: string, exclude: boolean) => {
    const current: Record<string, string[]> = Object.fromEntries(
      Object.entries(excludedByTable).map(([t, cols]) => [t, [...cols]]),
    );
    const set = new Set(current[table] ?? []);
    if (exclude) set.add(col);
    else set.delete(col);
    if (set.size > 0) current[table] = [...set];
    else delete current[table];
    setPendingKey(`${table}::${col}`);
    mutation.mutate(current);
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0">
        <div className="min-w-0 flex-1">
          <CardTitle className="text-base">Eliminar columnas</CardTitle>
          <CardDescription>
            Marca aquí las columnas que no deben aparecer en el dataset final.
            La columna se mantiene durante BRC (sigue disponible para reglas
            lógicas y derivadas) y se elimina al cerrar la ejecución, por lo
            que no llegará a entrenamiento, generación ni auditoría. Solo
            afecta a BRCs nuevas; las ya ejecutadas conservan sus datos.
          </CardDescription>
        </div>
        <CollapseToggle
          open={open}
          onToggle={() => setOpen((v) => !v)}
          ariaLabel={open ? "Contraer eliminación" : "Expandir eliminación"}
        />
      </CardHeader>
      {open && (
        <CardContent className="space-y-4">
          {isLoading && <Skeleton className="h-20 w-full" />}
          {isError && (
            <p className="text-sm text-destructive">
              No se pudo cargar el esquema autodetectado.
            </p>
          )}
          {!isLoading && !isError && tables.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No hay esquema disponible todavía.
            </p>
          )}
          {tables.map(([table, columns]) => {
            const excludedHere = new Set(excludedByTable[table] ?? []);
            return (
              <div key={table}>
                <h3 className="mb-2 font-mono text-sm font-medium">{table}</h3>
                <div className="flex flex-wrap gap-2">
                  {Object.keys(columns).map((col) => {
                    const isExcluded = excludedHere.has(col);
                    const isPending =
                      mutation.isPending && pendingKey === `${table}::${col}`;
                    return (
                      <span
                        key={col}
                        className={
                          "flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs " +
                          (isExcluded
                            ? "border-destructive/40 bg-destructive/5 text-muted-foreground"
                            : "bg-card")
                        }
                      >
                        <span
                          className={
                            "font-mono " + (isExcluded ? "line-through" : "")
                          }
                        >
                          {col}
                        </span>
                        <button
                          type="button"
                          title={
                            isExcluded
                              ? `Restaurar '${col}'`
                              : `Eliminar '${col}' tras BRC`
                          }
                          disabled={isPending}
                          onClick={() => toggle(table, col, !isExcluded)}
                          className={
                            "rounded p-0.5 disabled:opacity-40 " +
                            (isExcluded
                              ? "text-muted-foreground/70 hover:bg-foreground/10 hover:text-foreground"
                              : "text-muted-foreground/60 hover:bg-destructive/10 hover:text-destructive")
                          }
                        >
                          {isExcluded ? (
                            <RotateCcw className="h-3.5 w-3.5" />
                          ) : (
                            <Trash2 className="h-3.5 w-3.5" />
                          )}
                        </button>
                      </span>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </CardContent>
      )}
    </Card>
  );
}
