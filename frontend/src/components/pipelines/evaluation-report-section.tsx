"use client";

// EvaluationReportSection
// ─────────────────────────────────────────────────────────────────────────────
// Shows the structured HTML evaluation report for a completed evaluation run.
//
// • Score badges (composite 0–1 scores, higher = better) with colour annotations
//   — Utilidad can legitimately be empty ("—") when no predictive use case is
//     configured; the badge surfaces an info hint in that case (not an error)
// • Sandboxed iframe embedding the full HTML report inline (open by default)
// • Buttons: open in new tab, download zip

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Download, ExternalLink, FileText, Info, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { API_BASE_URL } from "@/lib/api";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Scores {
    global_score: number | null;
    fidelity_score: number | null;
    privacy_score: number | null;
    utility_score: number | null;
}

interface Summary {
    fidelity: Record<string, number | null>;
    privacy: Record<string, number | null>;
    utility: Record<string, number | null>;
}

interface ReportData {
    scores: Scores;
    summary: Summary;
    metadata: Record<string, string | null>;
}

// ── Threshold helpers ─────────────────────────────────────────────────────────

type Level = "good" | "warning" | "bad" | "unknown";

/** For composite normalized scores (0–1) only — higher IS always better here. */
function compositeLevel(value: number | null | undefined): Level {
    if (value == null) return "unknown";
    if (value >= 0.75) return "good";
    if (value >= 0.50) return "warning";
    return "bad";
}

const LEVEL_CLASSES: Record<Level, string> = {
    good: "border-green-300 bg-green-50 text-green-800",
    warning: "border-amber-300 bg-amber-50 text-amber-800",
    bad: "border-red-300 bg-red-50 text-red-800",
    unknown: "border-border bg-muted text-muted-foreground",
};

const LEVEL_ICON: Record<Level, React.ReactNode> = {
    good: <CheckCircle2 className="h-4 w-4 shrink-0" />,
    warning: <AlertTriangle className="h-4 w-4 shrink-0" />,
    bad: <XCircle className="h-4 w-4 shrink-0" />,
    unknown: null,
};

// ── ScoreBadge ────────────────────────────────────────────────────────────────
// Used for the four composite scores where higher IS always better.

function ScoreBadge({
    label,
    value,
    tooltip,
    emptyHint,
}: {
    label: string;
    value: number | null | undefined;
    tooltip?: string;
    /** Shown (with an info icon) when the score is empty — clarifies that "—"
     *  is a missing configuration, not a failed computation. */
    emptyHint?: string;
}) {
    const level = compositeLevel(value);
    const display = value == null ? "—" : `${(value * 100).toFixed(1)} %`;
    const showHint = value == null && Boolean(emptyHint);
    return (
        <div
            className={`flex flex-col items-center gap-1 rounded-xl border px-4 py-3 text-center ${LEVEL_CLASSES[level]}`}
            title={showHint ? emptyHint : tooltip}
        >
            <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide opacity-70">
                {LEVEL_ICON[level]}
                {label}
            </div>
            <span className="flex items-center gap-1.5 text-2xl font-bold tabular-nums">
                {display}
                {showHint && <Info className="h-4 w-4 opacity-60" aria-label={emptyHint} />}
            </span>
        </div>
    );
}

// ── Main component ─────────────────────────────────────────────────────────────

export function EvaluationReportSection({ evaluationId }: { evaluationId: string }) {
    const [iframeOpen, setIframeOpen] = useState(true);
    const reportDataQuery = useQuery<ReportData>({
        queryKey: ["evaluation-report-data", evaluationId],
        queryFn: async () => {
            const res = await fetch(`${API_BASE_URL}/evaluations/${evaluationId}/report-data`);
            if (!res.ok) throw new Error("No se pudo cargar el reporte");
            return res.json();
        },
    });

    const reportUrl = `${API_BASE_URL}/evaluations/${evaluationId}/report`;
    const downloadUrl = `${API_BASE_URL}/evaluations/${evaluationId}/download`;

    return (
        <div className="space-y-4">
            {/* Header row */}
            <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 text-sm font-medium">
                    <FileText className="h-4 w-4 text-purple-600" />
                    Reporte de evaluación
                </div>
                <div className="flex items-center gap-2">
                    <a href={reportUrl} target="_blank" rel="noopener noreferrer">
                        <Button type="button" size="sm" variant="outline">
                            <ExternalLink className="mr-1.5 h-3.5 w-3.5" />
                            Abrir en nueva pestaña
                        </Button>
                    </a>
                    <a href={downloadUrl} download>
                        <Button type="button" size="sm" variant="outline">
                            <Download className="mr-1.5 h-3.5 w-3.5" />
                            Descargar (zip)
                        </Button>
                    </a>
                </div>
            </div>

            {/* Score badges */}
            {reportDataQuery.isLoading && (
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    {Array.from({ length: 4 }).map((_, i) => (
                        <Skeleton key={i} className="h-20 rounded-xl" />
                    ))}
                </div>
            )}

            {reportDataQuery.data && (
                <>
                    {/* Composite scores — these ARE normalized 0–1 where higher = better */}
                    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                        <ScoreBadge
                            label="Global"
                            value={reportDataQuery.data.scores.global_score}
                            tooltip="Puntuación global combinada: media de los tres ejes. Rango 0–1, mayor = mejor."
                        />
                        <ScoreBadge
                            label="Fidelidad"
                            value={reportDataQuery.data.scores.fidelity_score}
                            tooltip="Grado en que las distribuciones sintéticas reproducen las reales. Rango 0–1."
                        />
                        <ScoreBadge
                            label="Privacidad"
                            value={reportDataQuery.data.scores.privacy_score}
                            tooltip="Nivel de protección frente a re-identificación y memorización. Rango 0–1."
                        />
                        <ScoreBadge
                            label="Utilidad"
                            value={reportDataQuery.data.scores.utility_score}
                            tooltip="Utilidad relativa: rendimiento de un modelo entrenado con datos sintéticos frente al mismo modelo entrenado con los reales. Rango 0–1, mayor = mejor. No mide si el sintético predice «bien» en absoluto, sino cuánto conserva respecto a lo que daban los reales."
                            emptyHint="«—» no es un fallo: la utilidad necesita que definas el caso de uso (columna objetivo y tipo de tarea, o análisis estadísticos) en la configuración de la evaluación. Sin esa definición no puede calcularse."
                        />
                    </div>
                </>
            )}

            {reportDataQuery.isError && (
                <p className="text-sm text-destructive">
                    No se pudo cargar los datos de métricas.
                </p>
            )}

            {/* Inline HTML report — collapsible */}
            <div className="overflow-hidden rounded-xl border bg-background shadow-sm">
                <button
                    type="button"
                    onClick={() => setIframeOpen((v) => !v)}
                    className="flex w-full items-center justify-between gap-2 px-4 py-3 text-sm font-medium hover:bg-muted/40 transition-colors"
                >
                    <span className="flex items-center gap-2 text-muted-foreground">
                        <FileText className="h-4 w-4" />
                        Informe HTML completo
                    </span>
                    {iframeOpen
                        ? <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
                        : <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                    }
                </button>
                {iframeOpen && (
                    <iframe
                        src={reportUrl}
                        title="Reporte HTML de evaluación"
                        className="h-[700px] w-full border-t"
                        sandbox="allow-scripts allow-same-origin"
                        loading="lazy"
                    />
                )}
            </div>
        </div>
    );
}
