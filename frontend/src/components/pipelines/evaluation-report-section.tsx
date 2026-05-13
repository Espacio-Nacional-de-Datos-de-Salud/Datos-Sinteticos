"use client";

// EvaluationReportSection
// ─────────────────────────────────────────────────────────────────────────────
// Shows the structured HTML evaluation report for a completed evaluation run.
//
// • Score badges (composite 0–1 scores, higher = better) with colour annotations
// • Per-metric rows showing RAW values with thresholds per metric direction
//   (some metrics: lower = better; some: higher = better; some: target ≈ 0.5)
// • Sandboxed iframe embedding the full HTML report inline
// • Buttons: open in new tab, download zip

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Download, ExternalLink, FileText, XCircle } from "lucide-react";

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
}: {
    label: string;
    value: number | null | undefined;
    tooltip?: string;
}) {
    const level = compositeLevel(value);
    const display = value == null ? "—" : `${(value * 100).toFixed(1)} %`;
    return (
        <div
            className={`flex flex-col items-center gap-1 rounded-xl border px-4 py-3 text-center ${LEVEL_CLASSES[level]}`}
            title={tooltip}
        >
            <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide opacity-70">
                {LEVEL_ICON[level]}
                {label}
            </div>
            <span className="text-2xl font-bold tabular-nums">{display}</span>
        </div>
    );
}

// ── MetricRow ─────────────────────────────────────────────────────────────────
// Shows the RAW metric value + an explicit "ideal" hint + colour.

interface MetricDef {
    label: string;
    /** Raw value to display as-is (no normalization). */
    rawValue: number | null | undefined;
    /** How to format rawValue for display. */
    format: "decimal4" | "decimal2" | "integer" | "pct1";
    /** Colour level based on the metric's own thresholds/direction. */
    level: Level;
    /** Short hint shown in the tag, e.g. "↓ ideal: 0" or "≈ ideal: 0.5". */
    ideal: string;
    tooltip: string;
}

function fmt(value: number | null | undefined, format: MetricDef["format"]): string {
    if (value == null) return "—";
    switch (format) {
        case "decimal4": return value.toFixed(4);
        case "decimal2": return value.toFixed(2);
        case "integer": return Math.round(value).toString();
        case "pct1": return `${(value * 100).toFixed(1)} %`;
    }
}

function MetricRow({ metric }: { metric: MetricDef }) {
    return (
        <div className="flex items-start justify-between gap-2 py-1.5 text-sm">
            <span className="flex items-center gap-1.5 text-muted-foreground">
                {LEVEL_ICON[metric.level]}
                <span title={metric.tooltip} className="leading-snug">{metric.label}</span>
            </span>
            <span className="flex shrink-0 flex-col items-end gap-0.5">
                <span
                    className={`rounded px-1.5 py-0.5 font-mono text-xs font-semibold ${LEVEL_CLASSES[metric.level]}`}
                >
                    {fmt(metric.rawValue, metric.format)}
                </span>
                <span className="text-[10px] text-muted-foreground">{metric.ideal}</span>
            </span>
        </div>
    );
}

// ── Metric threshold configuration ───────────────────────────────────────────
//
// Centralised table of per-metric thresholds and directions.
// Direction variants:
//   "higher"  — larger raw value is better  (good >= t.good, warning >= t.warning)
//   "lower"   — smaller raw value is better (good <= t.good, warning <= t.warning)
//   "target"  — distance to t.target determines quality (good if |v-target| <= t.good)
//   "none"    — reference only, no colour applied

type ThresholdConfig =
    | { direction: "higher"; good: number; warning: number }
    | { direction: "lower"; good: number; warning: number }
    | { direction: "target"; target: number; good: number; warning: number }
    | { direction: "none" };

export const METRIC_THRESHOLDS = {
    // ── Fidelidad ──────────────────────────────────────────────────────────
    /** Jensen-Shannon divergence on marginals. Lower = more faithful. */
    jsd: { direction: "lower", good: 0.05, warning: 0.15 } as ThresholdConfig,
    /** Inverse KL divergence, normalised 0–1. Higher = better. */
    inv_kl: { direction: "higher", good: 0.90, warning: 0.70 } as ThresholdConfig,
    /** 1 − TVD, averaged across columns. Higher = better. */
    inv_tvd: { direction: "higher", good: 0.75, warning: 0.50 } as ThresholdConfig,
    /** Correlation-matrix distance. Lower = better. */
    cmd: { direction: "lower", good: 0.10, warning: 0.30 } as ThresholdConfig,
    /** Confidence-interval overlap. Higher = better. */
    cio: { direction: "higher", good: 0.75, warning: 0.50 } as ThresholdConfig,

    // ── Privacidad ─────────────────────────────────────────────────────────
    /** Distance to nearest real record. Higher = less re-id risk. */
    dcr: { direction: "higher", good: 1.0, warning: 0.5 } as ThresholdConfig,
    /** Nearest-neighbour distance ratio. Higher = better. */
    nndr: { direction: "higher", good: 0.95, warning: 0.80 } as ThresholdConfig,
    /** Minimum k-anonymity group size. Higher = more anonymous. */
    k_anonymity: { direction: "higher", good: 5, warning: 2 } as ThresholdConfig,
    /** Exact-match rate. Lower = fewer real copies. */
    emr: { direction: "lower", good: 0.00, warning: 0.01 } as ThresholdConfig,
    /** MLP detection score. Should be ≈ 0.5 (indistinguishable). */
    detection_mlp: { direction: "target", target: 0.5, good: 0.05, warning: 0.15 } as ThresholdConfig,

    // ── Utilidad ───────────────────────────────────────────────────────────
    /** R² reference (trained & evaluated on real data). Informational only. */
    r2_ref: { direction: "none" } as ThresholdConfig,
    /** R² trained on synthetic, evaluated on real OOD. Higher = more useful. */
    r2_syn_ood: { direction: "higher", good: 0.50, warning: 0.30 } as ThresholdConfig,
} as const;

/** Compute a Level from a raw value using a ThresholdConfig entry. */
function applyThreshold(value: number | null | undefined, cfg: ThresholdConfig): Level {
    if (value == null) return "unknown";
    if (cfg.direction === "none") return "unknown";
    if (cfg.direction === "higher") {
        return value >= cfg.good ? "good" : value >= cfg.warning ? "warning" : "bad";
    }
    if (cfg.direction === "lower") {
        return value <= cfg.good ? "good" : value <= cfg.warning ? "warning" : "bad";
    }
    // target
    const dev = Math.abs(value - cfg.target);
    return dev <= cfg.good ? "good" : dev <= cfg.warning ? "warning" : "bad";
}

// ── Per-axis metric definitions ───────────────────────────────────────────────

function buildAxisMetrics(summary: Summary): { label: string; metrics: MetricDef[] }[] {
    const { fidelity: fi, privacy: pr, utility: ut } = summary;
    const T = METRIC_THRESHOLDS;

    return [
        {
            label: "Fidelidad",
            metrics: [
                {
                    label: "JSD marginal",
                    rawValue: fi.jsd,
                    format: "decimal4",
                    level: applyThreshold(fi.jsd, T.jsd),
                    ideal: "↓ ideal: 0",
                    tooltip: "Distancia Jensen-Shannon entre distribuciones marginales. Menor = más fiel.",
                },
                {
                    label: "KL divergencia inversa",
                    rawValue: fi.inv_kl,
                    format: "decimal4",
                    level: applyThreshold(fi.inv_kl, T.inv_kl),
                    ideal: "↑ ideal: 1",
                    tooltip: "KL invertida (1 = sin pérdida). Rango 0–1, mayor = mejor.",
                },
                {
                    label: "TVD complementaria media",
                    rawValue: fi.inv_tvd,
                    format: "decimal4",
                    level: applyThreshold(fi.inv_tvd, T.inv_tvd),
                    ideal: "↑ ideal: 1",
                    tooltip: "1 − TVD promedio por columna. Mayor = distribuciones más similares.",
                },
                {
                    label: "Dist. matriz correlación",
                    rawValue: fi.cmd,
                    format: "decimal4",
                    level: applyThreshold(fi.cmd, T.cmd),
                    ideal: "↓ ideal: 0",
                    tooltip: "Diferencia en matrices de correlación. Menor = correlaciones más preservadas.",
                },
                {
                    label: "Solapamiento IC",
                    rawValue: fi.cio,
                    format: "decimal4",
                    level: applyThreshold(fi.cio, T.cio),
                    ideal: "↑ ideal: 1",
                    tooltip: "Overlapping de intervalos de confianza de estadísticos clave. Mayor = mejor.",
                },
            ],
        },
        {
            label: "Privacidad",
            metrics: [
                {
                    label: "DCR (dist. al vecino real)",
                    rawValue: pr.dcr,
                    format: "decimal4",
                    level: applyThreshold(pr.dcr, T.dcr),
                    ideal: "↑ mayor = más distinto",
                    tooltip: "Distancia media al vecino real más cercano en espacio sintético. Mayor = menos riesgo de re-identificación.",
                },
                {
                    label: "NNDR",
                    rawValue: pr.nndr,
                    format: "decimal4",
                    level: applyThreshold(pr.nndr, T.nndr),
                    ideal: "↑ ideal: 1",
                    tooltip: "Ratio de distancias al vecino cercano. Cercano a 1 = sintéticos no copian patrones locales.",
                },
                {
                    label: "k-anonimato (sintético)",
                    rawValue: pr.k_anonymity,
                    format: "decimal2",
                    level: applyThreshold(pr.k_anonymity, T.k_anonymity),
                    ideal: "↑ ideal ≥ 5",
                    tooltip: "Número mínimo de registros indistinguibles por cuasi-identificadores. Mayor = mayor anonimato.",
                },
                {
                    label: "Tasa filas exactas (EMR)",
                    rawValue: pr.emr,
                    format: "pct1",
                    level: applyThreshold(pr.emr, T.emr),
                    ideal: "↓ ideal: 0 %",
                    tooltip: "Proporción de filas sintéticas idénticas a alguna real. Debe ser 0.",
                },
                {
                    label: "Detección MLP",
                    rawValue: pr.detection_mlp,
                    format: "decimal4",
                    level: applyThreshold(pr.detection_mlp, T.detection_mlp),
                    ideal: "≈ ideal: 0.5",
                    tooltip: "Score de un clasificador entrenado para distinguir reales/sintéticos. Cerca de 0.5 = indistinguibles.",
                },
            ],
        },
        {
            label: "Utilidad",
            metrics: [
                {
                    label: "Regresión lineal — referencia real",
                    rawValue: ut.linear_gt,
                    format: "decimal4",
                    level: applyThreshold(ut.linear_gt, T.r2_ref),
                    ideal: "(referencia)",
                    tooltip: "R² de regresión lineal entrenada y evaluada en datos reales. Valor de referencia; no se penaliza.",
                },
                {
                    label: "Regresión lineal — syn OOD",
                    rawValue: ut.linear_syn_ood,
                    format: "decimal4",
                    level: applyThreshold(ut.linear_syn_ood, T.r2_syn_ood),
                    ideal: "↑ mayor = mejor",
                    tooltip: "R² entrenando en sintéticos y evaluando en datos reales fuera de distribución (OOD). Mayor = más útil.",
                },
                {
                    label: "MLP — referencia real",
                    rawValue: ut.mlp_gt,
                    format: "decimal4",
                    level: applyThreshold(ut.mlp_gt, T.r2_ref),
                    ideal: "(referencia)",
                    tooltip: "R² de MLP entrenado y evaluado en datos reales. Valor de referencia; no se penaliza.",
                },
                {
                    label: "MLP — syn OOD",
                    rawValue: ut.mlp_syn_ood,
                    format: "decimal4",
                    level: applyThreshold(ut.mlp_syn_ood, T.r2_syn_ood),
                    ideal: "↑ mayor = mejor",
                    tooltip: "R² de MLP entrenado en sintéticos y evaluado en datos reales OOD. Mayor = más útil.",
                },
            ],
        },
    ];
}

// ── Main component ─────────────────────────────────────────────────────────────

export function EvaluationReportSection({ evaluationId }: { evaluationId: string }) {
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
                            tooltip="Capacidad predictiva preservada al usar sintéticos en lugar de reales. Rango 0–1."
                        />
                    </div>

                    {/* Per-axis raw metrics with per-metric direction/thresholds */}
                    <div className="grid gap-3 sm:grid-cols-3">
                        {buildAxisMetrics(reportDataQuery.data.summary).map((axis) => (
                            <div
                                key={axis.label}
                                className="rounded-lg border bg-card p-3 text-card-foreground shadow-sm"
                            >
                                <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                                    {axis.label}
                                </p>
                                <div className="divide-y">
                                    {axis.metrics.map((m) => (
                                        <MetricRow key={m.label} metric={m} />
                                    ))}
                                </div>
                            </div>
                        ))}
                    </div>
                </>
            )}

            {reportDataQuery.isError && (
                <p className="text-sm text-destructive">
                    No se pudo cargar los datos de métricas.
                </p>
            )}

            {/* Inline HTML report */}
            <div className="overflow-hidden rounded-xl border bg-background shadow-sm">
                <iframe
                    src={reportUrl}
                    title="Reporte HTML de evaluación"
                    className="h-[700px] w-full"
                    sandbox="allow-scripts allow-same-origin"
                    loading="lazy"
                />
            </div>
        </div>
    );
}
