"use client";

import { useQuery } from "@tanstack/react-query";
import { Download, ExternalLink } from "lucide-react";

import { Button } from "@/components/ui/button";
import { api, API_BASE_URL, type SimulationSummary } from "@/lib/api";
import { ArtifactShell, ArtifactStat } from "./artifact-shell";

export function SimulationArtifactCard({
  simulationId,
  onOpen,
}: {
  simulationId: string;
  onOpen: () => void;
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["simulation", simulationId],
    queryFn: async () => {
      const { data } = await api.get<SimulationSummary>(
        `/simulations/${simulationId}`,
      );
      return data;
    },
  });

  const datasetUrl = `${API_BASE_URL}/simulations/${simulationId}/download/synthetic-dataset`;

  return (
    <ArtifactShell
      label="Simulación"
      color="text-emerald-600"
      actions={
        <>
          <a
            href={datasetUrl}
            className="inline-flex items-center gap-1 rounded-md border border-border bg-background px-2 py-1 text-[11px] font-medium hover:bg-accent"
          >
            <Download className="h-3.5 w-3.5" /> Dataset sintético
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
        <span className="text-[11px] text-red-600">
          No se pudo cargar la simulación.
        </span>
      )}
      {data && (
        <>
          <ArtifactStat
            label="Filas generadas"
            value={
              data.sample_size != null ? data.sample_size.toLocaleString() : "—"
            }
          />
          <ArtifactStat label="Tablas" value={data.tables || "—"} />
          {data.model_accuracy != null && (
            <ArtifactStat
              label="Accuracy del modelo"
              value={`${(data.model_accuracy * 100).toFixed(2)}%`}
            />
          )}
          {data.simulation_name && (
            <ArtifactStat label="Nombre" value={data.simulation_name} />
          )}
        </>
      )}
    </ArtifactShell>
  );
}
