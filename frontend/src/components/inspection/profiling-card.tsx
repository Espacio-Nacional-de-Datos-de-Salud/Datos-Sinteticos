"use client";

import { Download, ExternalLink } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { API_BASE_URL, type ProfilingReports } from "@/lib/api";

// Per-table ydata-profiling reports rendered as iframes. The HTML is served
// straight off disk by the backend; we sandbox it because it's untrusted user
// data run through ydata's HTML template.
export function ProfilingCard({
  inspectionId,
  query,
}: {
  inspectionId: string | null;
  query: {
    data: ProfilingReports | undefined;
    isLoading: boolean;
    isError: boolean;
  };
}) {
  const reports = query.data?.reports ?? [];
  const hasReports = reports.length > 0;

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <CardTitle className="text-base">Profiling</CardTitle>
          <CardDescription>
            Informes de ydata-profiling por tabla. Se generan cuando la
            inspección se lanza con la casilla de profiling activada.
          </CardDescription>
        </div>
        {inspectionId && hasReports && (
          <a
            href={`${API_BASE_URL}/inspections/${inspectionId}/download/profiling`}
          >
            <Button variant="outline" size="sm" type="button">
              <Download className="mr-2 h-4 w-4" />
              Descargar todos (zip)
            </Button>
          </a>
        )}
      </CardHeader>
      <CardContent>
          {query.isLoading && <Skeleton className="h-[60vh] w-full" />}
          {query.isError && (
            <p className="text-sm text-destructive">
              No se pudieron cargar los informes de profiling.
            </p>
          )}
          {!query.isLoading && !query.isError && !hasReports && (
            <p className="text-sm text-muted-foreground">
              Esta inspección no tiene informes de profiling. Lanza otra
              inspección con la casilla <i>&quot;Generar informes de
                profiling&quot;</i> activada.
            </p>
          )}
          {hasReports && inspectionId && (
            <Tabs defaultValue={reports[0].table}>
              <TabsList className="flex-wrap">
                {reports.map((r) => (
                  <TabsTrigger key={r.table} value={r.table}>
                    {r.table}
                  </TabsTrigger>
                ))}
              </TabsList>
              {reports.map((r) => {
                const url = `${API_BASE_URL}/inspections/${inspectionId}/profiling/${encodeURIComponent(r.table)}`;
                return (
                  <TabsContent key={r.table} value={r.table}>
                    <div className="mb-2 flex items-center justify-between">
                      <span className="font-mono text-xs text-muted-foreground">
                        {r.filename}
                      </span>
                      <a href={url} target="_blank" rel="noreferrer">
                        <Button variant="outline" size="sm" type="button">
                          <ExternalLink className="mr-2 h-4 w-4" />
                          Abrir en pestaña nueva
                        </Button>
                      </a>
                    </div>
                    <iframe
                      title={`Profiling report ${r.table}`}
                      src={url}
                      className="h-[70vh] w-full rounded-md border bg-white"
                      sandbox="allow-scripts allow-same-origin allow-popups"
                    />
                  </TabsContent>
                );
              })}
            </Tabs>
          )}
        </CardContent>
    </Card>
  );
}
