"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { CollapseToggle } from "@/components/ui/collapse-toggle";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, API_BASE_URL, type FilePreview } from "@/lib/api";

// Visualización de datos con el MISMO formato que la tarjeta de
// selección de ficheros ("Visualización y eliminación de columnas"): una fila
// por tabla, "Ver muestra" (despliega una muestra inline) y "Ver completa"
// (abre un explorador paginado). A diferencia de aquella, lee de los endpoints
// de datos preprocesados de la inspección, no de /files/preview.
//
// Importante: estos datos son los preprocesados tras la autodetección y las
// exclusiones; NO son necesariamente los que verá el modelo, porque después
// puede pasar una fase de reglas de negocio que los altere.

const SAMPLE_ROWS = 50;

export function PreprocessedPreviewCard({
  inspectionId,
}: {
  inspectionId: string;
}) {
  const tablesQuery = useQuery({
    queryKey: ["inspections", inspectionId, "preprocessed", "tables"],
    queryFn: async () => {
      const { data } = await api.get<string[]>(
        `/inspections/${inspectionId}/preprocessed`,
      );
      return data;
    },
  });

  const tables = tablesQuery.data ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Visualización de datos</CardTitle>
        <CardDescription>
          Vista previa del dataset tras la autodetección y la eliminación de
          columnas. Expande una tabla para ver una muestra o ábrela completa.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {tablesQuery.isLoading && <Skeleton className="h-24 w-full" />}
        {tablesQuery.isError && (
          <p className="text-sm text-destructive">
            No se pudo cargar la vista previa.
          </p>
        )}
        {!tablesQuery.isLoading && !tablesQuery.isError && tables.length === 0 && (
          <p className="text-sm text-muted-foreground">
            No hay datos preprocesados disponibles para esta carga de datos.
          </p>
        )}
        {tables.map((table) => (
          <PreprocessedTableRow
            key={table}
            inspectionId={inspectionId}
            table={table}
          />
        ))}
        {tables.length > 0 && (
          <div className="border-t pt-3">
            <a
              href={`${API_BASE_URL}/inspections/${inspectionId}/download/preprocessed`}
              download
            >
              <Button type="button" size="sm" variant="outline">
                Descargar ZIP
              </Button>
            </a>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function PreprocessedTableRow({
  inspectionId,
  table,
}: {
  inspectionId: string;
  table: string;
}) {
  const [open, setOpen] = useState(false);
  const [explorerOpen, setExplorerOpen] = useState(false);

  // Inline sample — only fetched once the row is expanded.
  const sampleQuery = useQuery({
    queryKey: ["inspections", inspectionId, "preprocessed", table, "sample", SAMPLE_ROWS],
    enabled: open,
    queryFn: () =>
      fetchPreprocessed(inspectionId, table, {
        sample_rows: SAMPLE_ROWS,
        offset: 0,
        include_total: true,
      }),
  });

  const preview = sampleQuery.data;
  const rowsLabel =
    preview?.total_rows == null
      ? preview
        ? `${preview.rows.length} filas en la muestra`
        : ""
      : `${preview.total_rows.toLocaleString("es-ES")} filas`;

  return (
    <div className="rounded-md border">
      <div className="flex items-center justify-between gap-2 px-3 py-2">
        <div className="min-w-0 flex-1">
          <h3 className="truncate font-mono text-sm font-medium" title={table}>
            {table}
          </h3>
          {preview && (
            <p className="text-xs text-muted-foreground">
              {preview.columns.length} columnas
              {rowsLabel ? ` · ${rowsLabel}` : ""}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => setExplorerOpen(true)}
          >
            Ver completa
          </Button>
          <CollapseToggle
            open={open}
            onToggle={() => setOpen((v) => !v)}
            showLabel="Ver muestra"
            ariaLabel={open ? "Ocultar muestra" : "Mostrar muestra de la tabla"}
          />
        </div>
      </div>
      {open && (
        <div className="border-t">
          <div className="max-h-[60vh] overflow-auto bg-muted/30">
            {sampleQuery.isLoading && (
              <div className="p-4">
                <Skeleton className="h-48 w-full" />
              </div>
            )}
            {sampleQuery.isError && (
              <p className="p-3 text-xs text-destructive">
                No se pudo cargar la tabla.
              </p>
            )}
            {preview && !sampleQuery.isLoading && !sampleQuery.isError && (
              <Table>
                <TableHeader>
                  <TableRow>
                    {preview.columns.map((c) => (
                      <TableHead key={c} className="font-mono text-xs">
                        {c}
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {preview.rows.length === 0 ? (
                    <TableRow>
                      <TableCell
                        colSpan={Math.max(1, preview.columns.length)}
                        className="text-xs text-muted-foreground"
                      >
                        Sin filas para mostrar.
                      </TableCell>
                    </TableRow>
                  ) : (
                    preview.rows.map((row, i) => (
                      <TableRow key={i}>
                        {preview.columns.map((_, j) => (
                          <TableCell
                            key={j}
                            className="max-w-[220px] truncate font-mono text-xs"
                            title={row[j] ?? ""}
                          >
                            {row[j] ?? ""}
                          </TableCell>
                        ))}
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            )}
          </div>
        </div>
      )}
      {explorerOpen && (
        <PreprocessedExplorerDialog
          inspectionId={inspectionId}
          table={table}
          totalRows={preview?.total_rows ?? null}
          onClose={() => setExplorerOpen(false)}
        />
      )}
    </div>
  );
}

// Full-table explorer that pages through a preprocessed table server-side —
// the preprocessed-data analogue of TableExplorerDialog.
const EXPLORER_PAGE_SIZE = 100;

function PreprocessedExplorerDialog({
  inspectionId,
  table,
  totalRows,
  onClose,
}: {
  inspectionId: string;
  table: string;
  totalRows: number | null | undefined;
  onClose: () => void;
}) {
  const [page, setPage] = useState(0);
  const offset = page * EXPLORER_PAGE_SIZE;

  const pageQuery = useQuery({
    queryKey: ["inspections", inspectionId, "preprocessed", table, "page", offset, EXPLORER_PAGE_SIZE],
    queryFn: () =>
      fetchPreprocessed(inspectionId, table, {
        sample_rows: EXPLORER_PAGE_SIZE,
        offset,
        include_total: true,
      }),
  });

  const preview = pageQuery.data;
  const knownTotal = totalRows ?? preview?.total_rows ?? null;
  const totalPages =
    knownTotal == null ? null : Math.max(1, Math.ceil(knownTotal / EXPLORER_PAGE_SIZE));
  const hasNext =
    totalPages != null
      ? page + 1 < totalPages
      : (preview?.rows.length ?? 0) === EXPLORER_PAGE_SIZE;

  const fromRow = preview && preview.rows.length > 0 ? offset + 1 : 0;
  const toRow = preview ? offset + preview.rows.length : 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="flex h-[85vh] w-full max-w-6xl flex-col rounded-lg border bg-background shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b px-5 py-3">
          <div className="min-w-0">
            <h2 className="truncate font-mono text-base font-semibold" title={table}>
              {table}
            </h2>
            <p className="text-xs text-muted-foreground">
              {preview ? `${preview.columns.length} columnas` : "Cargando…"}
              {knownTotal != null
                ? ` · ${knownTotal.toLocaleString("es-ES")} filas en total`
                : ""}
            </p>
          </div>
          <Button type="button" size="sm" variant="outline" onClick={onClose}>
            Cerrar
          </Button>
        </div>

        <div className="flex-1 overflow-auto bg-muted/30">
          {pageQuery.isLoading && (
            <div className="p-4">
              <Skeleton className="h-64 w-full" />
            </div>
          )}
          {pageQuery.isError && (
            <p className="p-4 text-sm text-destructive">
              No se pudo cargar la página de la tabla.
            </p>
          )}
          {preview && !pageQuery.isLoading && !pageQuery.isError && (
            <Table>
              <TableHeader>
                <TableRow>
                  {preview.columns.map((c) => (
                    <TableHead key={c} className="font-mono text-xs">
                      {c}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {preview.rows.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={Math.max(1, preview.columns.length)}
                      className="text-xs text-muted-foreground"
                    >
                      Sin filas en esta página.
                    </TableCell>
                  </TableRow>
                ) : (
                  preview.rows.map((row, i) => (
                    <TableRow key={i}>
                      {preview.columns.map((_, j) => (
                        <TableCell
                          key={j}
                          className="max-w-[260px] truncate font-mono text-xs"
                          title={row[j] ?? ""}
                        >
                          {row[j] ?? ""}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          )}
        </div>

        <div className="flex items-center justify-between gap-3 border-t px-5 py-3 text-xs">
          <span className="text-muted-foreground">
            {fromRow > 0
              ? `Filas ${fromRow.toLocaleString("es-ES")}–${toRow.toLocaleString("es-ES")}`
              : "—"}
            {totalPages != null ? ` · Página ${page + 1} de ${totalPages}` : ""}
          </span>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={page === 0 || pageQuery.isLoading}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
            >
              Anterior
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={!hasNext || pageQuery.isLoading}
              onClick={() => setPage((p) => p + 1)}
            >
              Siguiente
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

async function fetchPreprocessed(
  inspectionId: string,
  table: string,
  params: { sample_rows: number; offset: number; include_total: boolean },
): Promise<FilePreview> {
  const { data } = await api.get<FilePreview>(
    `/inspections/${inspectionId}/preprocessed/${encodeURIComponent(table)}`,
    { params },
  );
  return data;
}
