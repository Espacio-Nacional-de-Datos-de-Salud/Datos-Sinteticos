"use client";

import { useQuery } from "@tanstack/react-query";
import { Download, ExternalLink, FileText } from "lucide-react";

import { Button } from "@/components/ui/button";
import { api, API_BASE_URL, type ModelSummary } from "@/lib/api";
import { ArtifactShell, ArtifactStat } from "./artifact-shell";

export function ModelArtifactCard({
  modelId,
  onOpen,
}: {
  modelId: string;
  onOpen: () => void;
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["model", modelId],
    queryFn: async () => {
      const { data } = await api.get<ModelSummary>(`/models/${modelId}`);
      return data;
    },
  });

  const reportUrl =
    data?.qa_report_filename
      ? `${API_BASE_URL}/models/${modelId}/reports/${data.qa_report_filename}`
      : null;
  const generatorUrl = `${API_BASE_URL}/models/${modelId}/download/generator`;

  return (
    <ArtifactShell
      label="Modelo"
      color="text-blue-600"
      actions={
        <>
          {reportUrl && (
            <a
              href={reportUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 rounded-md border border-border bg-background px-2 py-1 text-[11px] font-medium hover:bg-accent"
            >
              <FileText className="h-3.5 w-3.5" /> QA report
            </a>
          )}
          <a
            href={generatorUrl}
            className="inline-flex items-center gap-1 rounded-md border border-border bg-background px-2 py-1 text-[11px] font-medium hover:bg-accent"
          >
            <Download className="h-3.5 w-3.5" /> Generator
          </a>
          <Button type="button" size="sm" variant="outline" onClick={onOpen}>
            <ExternalLink className="mr-1 h-3.5 w-3.5" />
            Detalles
          </Button>
        </>
      }
    >
      {isLoading && (
        <span className="text-[11px] text-muted-foreground">Cargando…</span>
      )}
      {error && (
        <span className="text-[11px] text-red-600">No se pudo cargar el modelo.</span>
      )}
      {data && (
        <>
          <ArtifactStat
            label="Accuracy"
            value={
              data.accuracy != null
                ? `${(data.accuracy * 100).toFixed(2)}%`
                : "—"
            }
          />
          <ArtifactStat
            label="Filas entrenadas"
            value={
              data.train_size != null ? data.train_size.toLocaleString() : "—"
            }
          />
          <ArtifactStat label="Tablas" value={data.tables || "—"} />
          {data.model_name && (
            <ArtifactStat label="Nombre" value={data.model_name} />
          )}
        </>
      )}
    </ArtifactShell>
  );
}
