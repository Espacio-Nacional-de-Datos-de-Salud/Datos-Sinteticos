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

type UtilitySource = "both" | "predictive" | "statistical" | "none";

interface Scores {
    global_score: number | null;
    fidelity_score: number | null;
    privacy_score: number | null;
    utility_score: number | null;
    utility_relative_score?: number | null;
    utility_tests_score?: number | null;
    utility_source?: UtilitySource;
}

interface Summary {
    fidelity: Record<string, number | null>;
    privacy: Record<string, number | null>;
    utility: Record<string, number | null>;
}

interface ReportData {
    scores: Scores;
    summary: Summary;
    metadata: {
        evaluation_parameters?: { evaluated_tables?: string[] | null };
        [key: string]: unknown;
    };
}

/**
 * Caption under the score badges making explicit that the headline scores are
 * an UNWEIGHTED mean over the tables that were actually evaluated (which can be
 * a subset of the generated tables, and where every table counts the same
 * regardless of its size).
 */
function EvaluatedTablesNote({ data }: { data: ReportData }) {
    const tables = data.metadata?.evaluation_parameters?.evaluated_tables ?? [];
    const count = tables.length;
    if (count === 0) return null;
    return (
        <p className="flex items-start gap-1.5 text-[11px] leading-snug text-muted-foreground">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>
                Puntuaciones globales: media <strong>no ponderada</strong> de{" "}
                {count === 1 ? "la tabla evaluada" : `las ${count} tablas evaluadas`} (
                <span className="font-mono">{tables.join(", ")}</span>). Cada tabla pesa igual,
                con independencia de su tamaño, y pueden no ser todas las tablas generadas. Usa el
                desplegable de cada eje en el informe para ver el detalle por tabla.
            </span>
        </p>
    );
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

// ── Utility badge copy ──────────────────────────────────────────────────────
// Utilidad combina dos facetas: predictiva (rendimiento relativo TSTR) y
// estadística (pruebas definidas por el usuario). `utility_source` indica
// cuáles entraron en el valor mostrado.

const UTILITY_BASE_TOOLTIP =
    "Utilidad: combina la utilidad predictiva (rendimiento de un modelo entrenado con sintéticos frente a reales) y la estadística (indicadores definidos por el usuario). Rango 0–1, mayor = mejor.";

function utilityTooltip(source: UtilitySource | undefined): string {
    switch (source) {
        case "both":
            return `${UTILITY_BASE_TOOLTIP} Mostrado: media de ambas facetas.`;
        case "predictive":
            return `${UTILITY_BASE_TOOLTIP} Mostrado: solo utilidad predictiva (no se definieron pruebas estadísticas).`;
        case "statistical":
            return `${UTILITY_BASE_TOOLTIP} Mostrado: solo utilidad estadística (el modelo predictivo no produjo resultados).`;
        default:
            return UTILITY_BASE_TOOLTIP;
    }
}

/** Short caption under the badge value naming which facet it reflects. */
function utilityNote(source: UtilitySource | undefined): string | undefined {
    switch (source) {
        case "both":
            return "media predictiva + estadística";
        case "predictive":
            return "solo predictiva";
        case "statistical":
            return "solo estadística";
        default:
            return undefined;
    }
}

// ── ScoreBadge ────────────────────────────────────────────────────────────────
// Used for the four composite scores where higher IS always better.

function ScoreBadge({
    label,
    value,
    tooltip,
    emptyHint,
    note,
}: {
    label: string;
    value: number | null | undefined;
    tooltip?: string;
    /** Shown (with an info icon) when the score is empty — clarifies that "—"
     *  is a missing configuration, not a failed computation. */
    emptyHint?: string;
    /** Small caption under the value clarifying what the score reflects
     *  (e.g. that only one utility facet was available). */
    note?: string;
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
            {note && <span className="text-[10px] font-medium leading-tight opacity-70">{note}</span>}
        </div>
    );
}

// ── ReportPane ─────────────────────────────────────────────────────────────────
// Renders the score badges + inline HTML report for a single evaluated table.
// `table` is null for legacy evaluations stored in the flat (pre-multitable)
// layout, in which case the root report endpoints are used.

function ReportPane({ evaluationId, table }: { evaluationId: string; table: string | null }) {
    const [iframeOpen, setIframeOpen] = useState(true);
    const suffix = table ? `/${encodeURIComponent(table)}` : "";
    const reportDataQuery = useQuery<ReportData>({
        queryKey: ["evaluation-report-data", evaluationId, table],
        queryFn: async () => {
            const res = await fetch(
                `${API_BASE_URL}/evaluations/${evaluationId}/report-data${suffix}`,
            );
            if (!res.ok) throw new Error("No se pudo cargar el reporte");
            return res.json();
        },
    });

    const reportUrl = `${API_BASE_URL}/evaluations/${evaluationId}/report${suffix}`;

    return (
        <div className="space-y-4">
            <div className="flex justify-end">
                <a href={reportUrl} target="_blank" rel="noopener noreferrer">
                    <Button type="button" size="sm" variant="outline">
                        <ExternalLink className="mr-1.5 h-3.5 w-3.5" />
                        Abrir en nueva pestaña
                    </Button>
                </a>
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
                    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                        <ScoreBadge
                            label="Global"
                            value={reportDataQuery.data.scores.global_score}
                            tooltip="Puntuación global combinada (Fidelidad/Privacidad). Es la MEDIA NO PONDERADA de las tablas evaluadas: cada tabla pesa igual, sin importar su número de filas. Las tablas evaluadas pueden ser un subconjunto de las generadas (las que marcaste evaluar). Rango 0–1, mayor = mejor."
                        />
                        <ScoreBadge
                            label="Fidelidad"
                            value={reportDataQuery.data.scores.fidelity_score}
                            tooltip="Grado en que las distribuciones sintéticas reproducen las reales. Media no ponderada de las tablas evaluadas (todas pesan igual). Rango 0–1."
                        />
                        <ScoreBadge
                            label="Privacidad"
                            value={reportDataQuery.data.scores.privacy_score}
                            tooltip="Nivel de protección frente a re-identificación y memorización. Media no ponderada de las tablas evaluadas (todas pesan igual). Rango 0–1."
                        />
                        <ScoreBadge
                            label="Utilidad"
                            value={reportDataQuery.data.scores.utility_score}
                            tooltip={utilityTooltip(reportDataQuery.data.scores.utility_source)}
                            note={utilityNote(reportDataQuery.data.scores.utility_source)}
                            emptyHint="«—» no es un fallo: ni la utilidad predictiva (columna objetivo y tipo de tarea) ni la estadística (pruebas definidas por el usuario) pudieron calcularse. Define al menos una en la configuración de la evaluación, o revisa el informe por si alguna falló."
                        />
                    </div>
                    <EvaluatedTablesNote data={reportDataQuery.data} />
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

// ── Main component ─────────────────────────────────────────────────────────────

export function EvaluationReportSection({ evaluationId }: { evaluationId: string }) {
    const downloadUrl = `${API_BASE_URL}/evaluations/${evaluationId}/download`;

    // The evaluation produces a single unified report at the root: headline
    // scores are the per-axis mean across every evaluated table, and the report
    // itself lets the user switch the per-metric detail by table on each axis.
    return (
        <div className="space-y-4">
            {/* Header row */}
            <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 text-sm font-medium">
                    <FileText className="h-4 w-4 text-purple-600" />
                    Reporte de evaluación
                </div>
                <a href={downloadUrl} download>
                    <Button type="button" size="sm" variant="outline">
                        <Download className="mr-1.5 h-3.5 w-3.5" />
                        Descargar (zip)
                    </Button>
                </a>
            </div>

            <ReportPane evaluationId={evaluationId} table={null} />
        </div>
    );
}
