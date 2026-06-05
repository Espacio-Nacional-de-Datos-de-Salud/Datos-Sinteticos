"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, FileText, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { DownloadMenu } from "@/components/pipeline-step/download-menu";
import { EditableName } from "@/components/jobs/editable-name";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  deleteBrc,
  getBrcRulesSnapshot,
  renameBrc,
  type BRCSummary,
} from "@/lib/brc";
import { extractDetail } from "@/lib/errors";
import { statusBadgeVariant, translateStatus } from "@/lib/job-status";
import { formatDuration, formatJobDate } from "@/lib/utils";

// Historial global de ejecuciones BRC.
// Acciones por fila: seleccionar como activa, renombrar, eliminar,
// ver snapshot de rules.yaml, descargar (carpeta / dataset / profiling).
export function BRCHistoryCard({
  runs,
  activeBrcId,
  onSelectActive,
  inspectionNameById,
  isLoading,
  isError,
  errorMessage,
}: {
  runs: BRCSummary[];
  activeBrcId: string | null;
  onSelectActive: (brcId: string) => void;
  inspectionNameById: Record<string, string>;
  isLoading: boolean;
  isError?: boolean;
  errorMessage?: string;
}) {
  const queryClient = useQueryClient();
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const [snapshotOpenFor, setSnapshotOpenFor] = useState<string | null>(null);

  const deleteMutation = useMutation({
    mutationFn: deleteBrc,
    onSuccess: () => {
      toast.success("Ejecución eliminada");
      queryClient.invalidateQueries({
        queryKey: ["brc", "list"],
      });
    },
    onError: (err) => toast.error(`No se pudo eliminar: ${extractDetail(err)}`),
  });

  const renameMutation = useMutation({
    mutationFn: ({ brcId, name }: { brcId: string; name: string }) =>
      renameBrc(brcId, name),
    onSuccess: () => {
      toast.success("Renombrada");
      queryClient.invalidateQueries({
        queryKey: ["brc", "list"],
      });
    },
    onError: (err) =>
      toast.error(`No se pudo renombrar: ${extractDetail(err)}`),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Ejecuciones previas</CardTitle>
        <CardDescription>
          Cada ejecución guarda su propio snapshot de <code>rules.yaml</code>{" "}
          y su dataset preprocesado. Selecciona una para que alimente el entreno
          y la sección de Resultados.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-32 w-full" />
        ) : isError ? (
          <p className="text-sm text-destructive">
            No se pudo cargar el historial
            {errorMessage ? `: ${errorMessage}` : "."}
          </p>
        ) : runs.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No hay ejecuciones previas de reglas de negocio.
          </p>
        ) : (
          <Table className="table-fixed">
            <TableHeader>
              <TableRow>
                <TableHead style={{ width: "21%" }}>Nombre</TableHead>
                <TableHead style={{ width: "13%" }} className="pr-4">
                  Estado
                </TableHead>
                <TableHead style={{ width: "27%" }}>
                  Tablas / Carga de Datos
                </TableHead>
                <TableHead style={{ width: "7%" }}>Reglas</TableHead>
                <TableHead style={{ width: "14%" }}>Fecha</TableHead>
                <TableHead style={{ width: "8%" }}>Duración</TableHead>
                <TableHead style={{ width: "10%" }} className="text-right">
                  Acciones
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.map((run) => {
                const isActive = run.brc_id === activeBrcId;
                const isCompleted = run.status === "completed";
                const tableNames = Object.keys(run.tables ?? {});
                const tablesLabel = tableNames.join(", ");
                const inspectionName =
                  inspectionNameById[run.inspection_id] ?? run.inspection_id;
                return (
                  <TableRow
                    key={run.brc_id}
                    onClick={() => isCompleted && onSelectActive(run.brc_id)}
                    aria-selected={isActive}
                    className={
                      (isActive
                        ? "bg-primary/10 hover:bg-primary/10 "
                        : isCompleted
                          ? "cursor-pointer hover:bg-accent/40 "
                          : "opacity-60 ") + "transition-colors"
                    }
                  >
                    <TableCell
                      className="max-w-[18rem] overflow-hidden"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <div className="flex items-center gap-2">
                        <EditableName
                          name={run.brc_name || run.brc_id}
                          existingNames={runs
                            .filter((r) => r.brc_id !== run.brc_id)
                            .map((r) => r.brc_name || r.brc_id)}
                          onSave={async (name) => {
                            await renameMutation.mutateAsync({
                              brcId: run.brc_id,
                              name,
                            });
                          }}
                        />
                      </div>
                      <p className="mt-0.5 truncate font-mono text-[10px] text-muted-foreground">
                        {run.brc_id}
                      </p>
                    </TableCell>
                    <TableCell className="pr-4">
                      <Badge variant={statusBadgeVariant(run.status)}>
                        {translateStatus(run.status)}
                      </Badge>
                    </TableCell>
                    <TableCell className="min-w-0 overflow-hidden">
                      <span
                        className="block truncate font-mono text-xs"
                        title={tablesLabel}
                      >
                        {tablesLabel || "—"}
                      </span>
                      <span
                        className="block truncate text-[10px] text-muted-foreground"
                        title={inspectionName}
                      >
                        {inspectionName}
                      </span>
                    </TableCell>
                    <TableCell className="text-xs">{run.rules_count}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {formatJobDate(run.timestamp)}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {formatDuration(run.duration_seconds)}
                    </TableCell>
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center justify-end gap-1">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSnapshotOpenFor(run.brc_id);
                          }}
                          aria-label="Ver snapshot de rules.yaml"
                          title="Ver snapshot de rules.yaml"
                          className="rounded p-1 text-muted-foreground hover:bg-primary/10 hover:text-primary"
                        >
                          <FileText className="h-3.5 w-3.5" />
                        </button>
                        <DownloadMenu
                          ariaLabel="Descargas"
                          options={[
                            {
                              label: "Carpeta completa (.zip)",
                              href: `/business-rules-configurations/${run.brc_id}/download`,
                            },
                            {
                              label: "Dataset preprocesado (.zip)",
                              href: `/business-rules-configurations/${run.brc_id}/download/dataset`,
                            },
                            {
                              label: "Informes profiling (.zip)",
                              href: `/business-rules-configurations/${run.brc_id}/download/profiling`,
                            },
                          ]}
                          disabled={!isCompleted}
                        />
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setPendingDelete(run.brc_id);
                          }}
                          disabled={deleteMutation.isPending}
                          aria-label="Eliminar ejecución"
                          title="Eliminar ejecución"
                          className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-40"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>

      <ConfirmDialog
        open={!!pendingDelete}
        title="¿Eliminar ejecución?"
        description={
          pendingDelete
            ? `Se eliminará la carpeta de la ejecución "${pendingDelete}" del servidor (parquet, profiling y snapshot). No se puede deshacer.`
            : ""
        }
        confirmLabel="Eliminar"
        onConfirm={() => {
          if (pendingDelete) deleteMutation.mutate(pendingDelete);
          setPendingDelete(null);
        }}
        onCancel={() => setPendingDelete(null)}
      />

      {snapshotOpenFor && (
        <RulesSnapshotDialog
          brcId={snapshotOpenFor}
          onClose={() => setSnapshotOpenFor(null)}
        />
      )}
    </Card>
  );
}

function RulesSnapshotDialog({
  brcId,
  onClose,
}: {
  brcId: string;
  onClose: () => void;
}) {
  const snapshotQuery = useQuery({
    queryKey: ["brc", "rules-snapshot", brcId],
    queryFn: () => getBrcRulesSnapshot(brcId),
  });
  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-black/50"
        onClick={onClose}
        aria-hidden
      />
      <aside
        role="dialog"
        aria-label="Snapshot de rules.yaml"
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-2xl flex-col border-l bg-background shadow-xl"
      >
        <header className="flex items-start justify-between gap-2 border-b p-4">
          <div>
            <div className="text-xs text-muted-foreground">
              <span className="font-mono">{brcId}</span>
            </div>
            <h2 className="mt-1 text-base font-semibold">
              Snapshot de rules.yaml
            </h2>
          </div>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={onClose}
          >
            <ExternalLink className="mr-1.5 h-3.5 w-3.5" />
            Cerrar
          </Button>
        </header>
        <div className="flex-1 overflow-auto p-4">
          {snapshotQuery.isLoading ? (
            <Skeleton className="h-64 w-full" />
          ) : snapshotQuery.isError ? (
            <p className="text-sm text-destructive">
              No se pudo cargar el snapshot.
            </p>
          ) : (
            <pre className="whitespace-pre-wrap break-words rounded-md border bg-muted/30 p-3 font-mono text-xs">
              {snapshotQuery.data}
            </pre>
          )}
        </div>
      </aside>
    </>
  );
}
