"use client";

import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Trash2 } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { CollapseToggle } from "@/components/ui/collapse-toggle";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { api, type Autodetect } from "@/lib/api";

// Post-preprocessing column deletion. Uses the same destructive endpoint as
// the × button in the Inspección > Tipos card — both pages share the
// ["autodetect", inspectionId] cache, so deletions made here also reflect in
// the inspection page (and vice versa).
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
  const [pending, setPending] = useState<{ table: string; col: string } | null>(
    null,
  );
  const queryClient = useQueryClient();

  const tables = useMemo(
    () => Object.entries(autodetect?.encoding_types ?? {}),
    [autodetect?.encoding_types],
  );

  const deleteMutation = useMutation({
    mutationFn: async ({ table, col }: { table: string; col: string }) => {
      if (!inspectionId) throw new Error("Sin inspección activa");
      const { data } = await api.put<Autodetect>(
        `/inspections/${inspectionId}/autodetect/excluded-columns`,
        { excluded_columns: { [table]: [col] } },
      );
      return data;
    },
    onSuccess: (data) => {
      toast.success("Columna eliminada y datos preprocesados actualizados.");
      queryClient.setQueryData(["autodetect", inspectionId], data);
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Error desconocido";
      toast.error(`No se pudo eliminar la columna: ${msg}`);
    },
  });

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0">
        <div className="min-w-0 flex-1">
          <CardTitle className="text-base">Eliminar columnas</CardTitle>
          <CardDescription>
            Tras revisar el profiling, elimina aquí columnas que no aportan
            valor al modelo. La acción es destructiva: la columna desaparece
            del esquema y de los datos preprocesados; para recuperarla habría
            que volver a lanzar la carga de datos.
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
          {tables.map(([table, columns]) => (
            <div key={table}>
              <h3 className="mb-2 font-mono text-sm font-medium">{table}</h3>
              <div className="flex flex-wrap gap-2">
                {Object.keys(columns).map((col) => (
                  <span
                    key={col}
                    className="flex items-center gap-1.5 rounded-md border bg-card px-2 py-1 text-xs"
                  >
                    <span className="font-mono">{col}</span>
                    <button
                      type="button"
                      title={`Eliminar '${col}'`}
                      disabled={deleteMutation.isPending}
                      onClick={() => setPending({ table, col })}
                      className="rounded p-0.5 text-muted-foreground/60 hover:bg-destructive/10 hover:text-destructive disabled:opacity-40"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </span>
                ))}
              </div>
            </div>
          ))}
        </CardContent>
      )}
      <ConfirmDialog
        open={!!pending}
        title="¿Eliminar columna?"
        description={
          pending
            ? `Se eliminará "${pending.col}" de "${pending.table}" del esquema y de los datos preprocesados. Esta acción no es reversible sin volver a lanzar la carga de datos.`
            : ""
        }
        confirmLabel="Eliminar"
        onConfirm={() => {
          if (pending) deleteMutation.mutate(pending);
          setPending(null);
        }}
        onCancel={() => setPending(null)}
      />
    </Card>
  );
}
