"use client";

import { useQuery } from "@tanstack/react-query";
import { Download, ExternalLink } from "lucide-react";

import { Button } from "@/components/ui/button";
import { api, API_BASE_URL, type EvaluationSummary } from "@/lib/api";
import { ArtifactShell, ArtifactStat } from "./artifact-shell";

export function EvaluationArtifactCard({
  evaluationId,
  onOpen,
}: {
  evaluationId: string;
  onOpen: () => void;
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["evaluation", evaluationId],
    queryFn: async () => {
      const { data } = await api.get<EvaluationSummary>(
        `/evaluations/${evaluationId}`,
      );
      return data;
    },
  });

  const downloadUrl = `${API_BASE_URL}/evaluations/${evaluationId}/download`;

  return (
    <ArtifactShell
      label="Evaluación"
      color="text-purple-600"
      actions={
        <>
          <a
            href={downloadUrl}
            className="inline-flex items-center gap-1 rounded-md border border-border bg-background px-2 py-1 text-[11px] font-medium hover:bg-accent"
          >
            <Download className="h-3.5 w-3.5" /> Reporte (zip)
          </a>
          <Button type="button" size="sm" variant="outline" onClick={onOpen}>
            <ExternalLink className="mr-1 h-3.5 w-3.5" />
            Auditoría
          </Button>
        </>
      }
    >
      {isLoading && (
        <span className="text-[11px] text-muted-foreground">Cargando…</span>
      )}
      {error && (
        <span className="text-[11px] text-red-600">
          No se pudo cargar la evaluación.
        </span>
      )}
      {data && (
        <>
          <ArtifactStat label="Estado" value={data.status} />
          {data.metrics_evaluated && data.metrics_evaluated.length > 0 && (
            <ArtifactStat
              label="Métricas"
              value={data.metrics_evaluated.join(", ")}
            />
          )}
          {data.evaluation_name && (
            <ArtifactStat label="Nombre" value={data.evaluation_name} />
          )}
        </>
      )}
    </ArtifactShell>
  );
}
