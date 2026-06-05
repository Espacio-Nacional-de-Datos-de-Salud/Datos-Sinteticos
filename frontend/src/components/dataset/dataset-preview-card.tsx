"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { API_BASE_URL, type FilePreview } from "@/lib/api";

const PAGE_SIZE = 100;

export type DatasetFetcher = (
  table: string,
  params: { sample_rows: number; offset: number; include_total: boolean },
) => Promise<FilePreview>;

// Reusable preview card for any persisted dataset (preprocessed, synthetic, …).
// Shows a table picker plus a paginated row viewer, and offers a download link
// for the whole dataset when ``downloadHref`` is provided.
export function DatasetPreviewCard({
  title,
  description,
  cacheKey,
  tables,
  isLoadingTables,
  isError,
  fetcher,
  downloadHref,
  getProfilingUrl,
  emptyMessage = "No hay datos disponibles.",
}: {
  title: string;
  description?: string;
  // Used as a stable prefix in the react-query cache key so two instances
  // (e.g. preprocessed + synthetic) do not collide.
  cacheKey: string;
  tables: string[];
  isLoadingTables: boolean;
  isError: boolean;
  fetcher: DatasetFetcher;
  downloadHref?: string;
  /** Optional: given the currently-active table name, returns the URL for its
   * ydata-profiling HTML report, or null/undefined when not available. */
  getProfilingUrl?: (table: string) => string | null | undefined;
  emptyMessage?: string;
}) {
  const [active, setActive] = useState<string | null>(null);
  const [page, setPage] = useState(0);

  useEffect(() => {
    if (active == null && tables.length > 0) {
      setActive(tables[0]);
    }
    if (active != null && tables.length > 0 && !tables.includes(active)) {
      setActive(tables[0]);
      setPage(0);
    }
  }, [tables, active]);

  const offset = page * PAGE_SIZE;
  const previewQuery = useQuery({
    queryKey: [cacheKey, active, offset, PAGE_SIZE],
    enabled: active != null,
    queryFn: () =>
      fetcher(active as string, {
        sample_rows: PAGE_SIZE,
        offset,
        include_total: true,
      }),
  });

  const preview = previewQuery.data;
  const total = preview?.total_rows ?? null;
  const totalPages = total == null ? null : Math.max(1, Math.ceil(total / PAGE_SIZE));
  const hasNext =
    totalPages != null
      ? page + 1 < totalPages
      : (preview?.rows.length ?? 0) === PAGE_SIZE;
  const fromRow = preview && preview.rows.length > 0 ? offset + 1 : 0;
  const toRow = preview ? offset + preview.rows.length : 0;

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <CardTitle className="text-base">{title}</CardTitle>
            {description && <CardDescription>{description}</CardDescription>}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {getProfilingUrl && active && getProfilingUrl(active) && (
              <Tooltip
                content="Abre el informe ydata-profiling de esta tabla en una nueva pestaña."
                side="top"
              >
                <a
                  href={getProfilingUrl(active)!}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <Button type="button" size="sm" variant="outline">
                    Ver profiling
                  </Button>
                </a>
              </Tooltip>
            )}
            {downloadHref && tables.length > 0 && (
              <a href={`${API_BASE_URL}${downloadHref}`} download>
                <Button type="button" size="sm" variant="outline">
                  Descargar ZIP
                </Button>
              </a>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoadingTables && <Skeleton className="h-24 w-full" />}
        {isError && (
          <p className="text-sm text-destructive">
            No se pudo cargar la vista previa.
          </p>
        )}
        {!isLoadingTables && !isError && tables.length === 0 && (
          <p className="text-sm text-muted-foreground">{emptyMessage}</p>
        )}
        {!isLoadingTables && !isError && tables.length > 0 && (
          <>
            <div className="flex flex-wrap gap-1.5">
              {tables.map((t) => {
                const isActive = t === active;
                return (
                  <button
                    key={t}
                    type="button"
                    onClick={() => {
                      setActive(t);
                      setPage(0);
                    }}
                    className={
                      "rounded border px-2 py-0.5 font-mono text-[11px] transition-all " +
                      (isActive
                        ? "border-primary bg-primary/10 text-foreground"
                        : "border-border bg-background text-foreground hover:border-primary hover:bg-primary/5")
                    }
                  >
                    {t}
                  </button>
                );
              })}
            </div>

            <div className="max-h-[60vh] overflow-auto rounded-md border bg-muted/30">
              {previewQuery.isLoading && (
                <div className="p-4">
                  <Skeleton className="h-48 w-full" />
                </div>
              )}
              {previewQuery.isError && (
                <p className="p-4 text-sm text-destructive">
                  No se pudo cargar la tabla.
                </p>
              )}
              {preview && !previewQuery.isLoading && !previewQuery.isError && (
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

            <div className="flex items-center justify-between gap-3 text-xs">
              <span className="text-muted-foreground">
                {preview
                  ? `${preview.columns.length} columnas`
                  : "Cargando…"}
                {fromRow > 0
                  ? ` · Filas ${fromRow.toLocaleString("es-ES")}–${toRow.toLocaleString("es-ES")}`
                  : ""}
                {total != null
                  ? ` · ${total.toLocaleString("es-ES")} en total`
                  : ""}
                {totalPages != null ? ` · Página ${page + 1} de ${totalPages}` : ""}
              </span>
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={page === 0 || previewQuery.isLoading}
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                >
                  Anterior
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={!hasNext || previewQuery.isLoading}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Siguiente
                </Button>
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
