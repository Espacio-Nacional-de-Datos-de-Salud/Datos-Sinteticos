"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
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
import { api, type FilePreview } from "@/lib/api";

// Page size for the full-table explorer. Big enough to feel like browsing,
// small enough that the JSON payload stays under a few hundred KB even on
// 100-column tables.
const EXPLORER_PAGE_SIZE = 100;

// Modal dialog that pages through a single file's rows server-side. Used
// when the user wants to scan more than the 50-row inline preview without
// loading the whole file into the browser.
export function TableExplorerDialog({
  path,
  table,
  totalRows,
  csvDelimiter,
  onClose,
}: {
  path: string;
  table: string;
  totalRows: number | null | undefined;
  csvDelimiter: string;
  onClose: () => void;
}) {
  const [page, setPage] = useState(0);
  const offset = page * EXPLORER_PAGE_SIZE;

  const pageQuery = useQuery({
    queryKey: ["files", "preview", "page", path, offset, EXPLORER_PAGE_SIZE, csvDelimiter],
    queryFn: async () => {
      const { data } = await api.post<FilePreview[]>("/files/preview", {
        paths: [path],
        sample_rows: EXPLORER_PAGE_SIZE,
        offset,
        csv_delimiter: csvDelimiter,
      });
      return data[0] ?? null;
    },
  });

  const preview = pageQuery.data;
  const knownTotal = totalRows ?? preview?.total_rows ?? null;
  const totalPages =
    knownTotal == null ? null : Math.max(1, Math.ceil(knownTotal / EXPLORER_PAGE_SIZE));
  // Without a known total we let the user advance until a page comes back
  // empty — same UX as a "load more" cursor, no extra round-trip needed.
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
            <h2 className="truncate font-mono text-base font-semibold" title={path}>
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
