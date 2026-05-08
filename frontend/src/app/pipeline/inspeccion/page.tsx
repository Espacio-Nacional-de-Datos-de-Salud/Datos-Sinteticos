// Inspección — step 2 of the pipeline wizard.
//
// Assumes raw files already exist on the server under backend/data/ (true
// upload lives in Ingesta, not yet implemented). Here we pick files, launch
// an inspection run, poll it to completion, then visualise the autodetected
// schema: primary keys, foreign keys, and per-column encoding types.
//
// Flow:
//   1. GET /files/                                -> server-side file list.
//   2. User selects one or more files.
//   3. Click "Iniciar Inspección" -> POST /inspections/.
//   4. Poll GET /inspections/{id} every 2s until status leaves in_progress.
//   5. On completion, GET /inspections/{id}/autodetect and render the
//      detected relationships + encoding types (read-only for now; editing
//      will land in a later iteration).

"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Database,
  Download,
  ExternalLink,
  Settings,
  Trash2,
  Upload,
  XCircle,
} from "lucide-react";
import { RulesEditor } from "@/components/config/rules-editor";
import { JobProgressPanel } from "@/components/jobs/job-progress";
import { EditableName } from "@/components/jobs/editable-name";
import { RelationshipsGraph } from "@/components/inspection/relationships-graph";
import axios from "axios";
import {
  API_BASE_URL,
  ENCODING_TYPES,
  api,
  type Autodetect,
  type DataFile,
  type FilePreview,
  type ForeignKey,
  type InspectionJob,
  type InspectionSummary,
  type ProfilingReports,
  type UploadStats,
  getUploadStats,
} from "@/lib/api";
import { ALLOW_SERVER_FILES as ALLOW_SERVER_FILES_FLAG } from "@/lib/features";
import { useIsDev } from "@/lib/mode";
import { WizardShell } from "@/components/layout/wizard-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const STORAGE_KEY = "ends.pipeline.currentInspectionId";

const EXT_FILTERS = ["csv", "parquet", "json"] as const;
type ExtFilter = (typeof EXT_FILTERS)[number] | "all";

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

// Color-code the MostlyAI encoding labels so related types are visually
// grouped. Kept here (not in api.ts) because it's purely presentational.
function typeBadgeClass(type: string): string {
  if (type.includes("NUMERIC")) return "bg-blue-100 text-blue-800 border-blue-200";
  if (type.includes("CATEGORICAL")) return "bg-amber-100 text-amber-800 border-amber-200";
  if (type.includes("DATETIME")) return "bg-violet-100 text-violet-800 border-violet-200";
  if (type.includes("CHARACTER")) return "bg-emerald-100 text-emerald-800 border-emerald-200";
  return "bg-muted text-muted-foreground";
}

// --------------------------------------------------------------------------
// Storage usage counter
// --------------------------------------------------------------------------
function UploadStorageBar({ stats }: { stats: UploadStats | undefined }) {
  if (!stats) return null;

  const { used_bytes, limit_bytes } = stats;
  const pct = limit_bytes > 0 ? Math.min((used_bytes / limit_bytes) * 100, 100) : 0;

  const barColor =
    pct >= 90
      ? "bg-red-500"
      : pct >= 70
        ? "bg-amber-500"
        : "bg-emerald-500";

  const textColor =
    pct >= 90
      ? "text-red-600"
      : pct >= 70
        ? "text-amber-600"
        : "text-muted-foreground";

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between text-xs">
        <span className={textColor}>
          {formatSize(used_bytes)} usados de {formatSize(limit_bytes)}
        </span>
        <span className={`font-medium tabular-nums ${textColor}`}>
          {pct.toFixed(0)}%
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={`h-full rounded-full transition-all duration-500 ${barColor}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {pct >= 90 && (
        <p className="text-xs text-red-600">
          Almacenamiento casi lleno. Borra algunos ficheros antes de subir más.
        </p>
      )}
    </div>
  );
}

export default function InspeccionPage() {
  const queryClient = useQueryClient();
  const [extFilter, setExtFilter] = useState<ExtFilter>("all");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [enableProfiling, setEnableProfiling] = useState<boolean>(true);
  // "uploads" in production; dev builds may toggle to see sample files already
  // present under backend/data/.
  const [sourceFilter, setSourceFilter] = useState<"uploads" | "server">(
    "uploads",
  );
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  // Start as null on both server and client to match SSR output, then load
  // the stored id from localStorage in an effect so the first client render
  // matches the server render (avoids a hydration mismatch on every piece of
  // DOM that branches on inspectionId).
  const [inspectionId, setInspectionId] = useState<string | null>(null);
  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    // Reading localStorage is intentionally deferred to a mount effect so
    // SSR and the first client render agree on `null`. Acceptable use of
    // setState-in-effect.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (stored) setInspectionId(stored);
  }, []);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [confirmCleanup, setConfirmCleanup] = useState(false);
  const [confirmPurge, setConfirmPurge] = useState(false);
  const [rulesOpen, setRulesOpen] = useState(false);
  // Server-files browsing is a dev-only convenience: in production the user
  // can only pick files they uploaded themselves. The legacy NEXT_PUBLIC_*
  // flag still acts as an override for CI / Docker, but the runtime Dev/Prod
  // toggle is the primary on/off switch now — flip it from the header.
  const isDev = useIsDev();
  const [allowServerFiles, setAllowServerFiles] = useState(ALLOW_SERVER_FILES_FLAG);
  useEffect(() => {
    setAllowServerFiles(ALLOW_SERVER_FILES_FLAG || isDev);
  }, [isDev]);

  const filesQuery = useQuery({
    queryKey: ["files", extFilter],
    queryFn: async () => {
      const ext = extFilter === "all" ? "" : extFilter;
      const { data } = await api.get<DataFile[]>("/files/", {
        params: ext ? { ext } : {},
      });
      return data;
    },
  });

  const uploadStatsQuery = useQuery({
    queryKey: ["upload-stats"],
    queryFn: getUploadStats,
    refetchInterval: 10_000,
  });

  const inspectionQuery = useQuery({
    queryKey: ["inspection", inspectionId],
    enabled: !!inspectionId,
    queryFn: async () => {
      const { data } = await api.get<InspectionSummary>(
        `/inspections/${inspectionId}`,
      );
      return data;
    },
    refetchInterval: (query) =>
      query.state.data?.status === "in_progress" ? 2000 : false,
  });

  const isCompleted = inspectionQuery.data?.status === "completed";

  // Autodetect only exists once the run has completed; gate the query on that.
  const autodetectQuery = useQuery({
    queryKey: ["autodetect", inspectionId],
    enabled: !!inspectionId && isCompleted,
    queryFn: async () => {
      const { data } = await api.get<Autodetect>(
        `/inspections/${inspectionId}/autodetect`,
      );
      return data;
    },
  });

  // Pristine auto-detected snapshot. Loaded once per inspection and used as
  // the comparison baseline for the "Restaurar autodetectado" buttons, which
  // must light up whenever the saved value diverges from the original — not
  // only when there are unsaved local edits.
  const originalQuery = useQuery({
    queryKey: ["autodetect", "original", inspectionId],
    enabled: !!inspectionId && isCompleted,
    queryFn: async () => {
      const { data } = await api.get<Autodetect>(
        `/inspections/${inspectionId}/autodetect/original`,
      );
      return data;
    },
  });

  // Local editable copy of the autodetect schema. Re-seeded from the server
  // value whenever the underlying object identity changes (new inspection
  // loaded, or after a successful save). Adjusts state during render rather
  // than in an effect to avoid a double-render and the cascading-effect lint
  // rule.
  const [draft, setDraft] = useState<Autodetect | null>(null);
  const [draftSource, setDraftSource] = useState<Autodetect | undefined>(
    undefined,
  );
  if (autodetectQuery.data !== draftSource) {
    setDraftSource(autodetectQuery.data);
    setDraft(autodetectQuery.data ? structuredClone(autodetectQuery.data) : null);
  }

  // Three independent baselines per section drive three buttons:
  //   - draft ≠ saved        -> "Guardar" enabled and "Descartar cambios" visible
  //   - saved ≠ original OR
  //     draft ≠ original     -> "Restaurar autodetectado" visible
  // The compound OR ensures the autodetected reset is reachable even when
  // the draft already matches the server's saved (non-pristine) value.
  const saved = autodetectQuery.data;
  const original = originalQuery.data;

  const relsDirtyVsSaved = useMemo(
    () =>
      !!draft &&
      !!saved &&
      JSON.stringify(draft.relationships) !== JSON.stringify(saved.relationships),
    [draft, saved],
  );
  const typesDirtyVsSaved = useMemo(
    () =>
      !!draft &&
      !!saved &&
      JSON.stringify(draft.encoding_types) !== JSON.stringify(saved.encoding_types),
    [draft, saved],
  );
  const relsDiffersFromOriginal = useMemo(
    () =>
      !!draft &&
      !!original &&
      JSON.stringify(draft.relationships) !== JSON.stringify(original.relationships),
    [draft, original],
  );
  const typesDiffersFromOriginal = useMemo(
    () =>
      !!draft &&
      !!original &&
      JSON.stringify(draft.encoding_types) !== JSON.stringify(original.encoding_types),
    [draft, original],
  );

  const saveRelationshipsMutation = useMutation({
    mutationFn: async (payload: Autodetect["relationships"]) => {
      const { data } = await api.put<Autodetect>(
        `/inspections/${inspectionId}/autodetect/relationships`,
        payload,
      );
      return data;
    },
    onSuccess: (data) => {
      toast.success("Relaciones actualizadas");
      queryClient.setQueryData(["autodetect", inspectionId], data);
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Error desconocido";
      toast.error(`No se pudieron guardar las relaciones: ${msg}`);
    },
  });

  const saveTypesMutation = useMutation({
    mutationFn: async (payload: Autodetect["encoding_types"]) => {
      const { data } = await api.put<Autodetect>(
        `/inspections/${inspectionId}/autodetect/encoding-types`,
        payload,
      );
      return data;
    },
    onSuccess: (data) => {
      toast.success("Tipos actualizados");
      queryClient.setQueryData(["autodetect", inspectionId], data);
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Error desconocido";
      toast.error(`No se pudieron guardar los tipos: ${msg}`);
    },
  });

  const saveRelationships = () => {
    if (!draft) return;
    saveRelationshipsMutation.mutate(draft.relationships);
  };

  const saveTypes = () => {
    if (!draft) return;
    saveTypesMutation.mutate(draft.encoding_types);
  };

  // Restore-to-autodetected pulls the pristine snapshot but only replaces
  // the requested section in the draft, leaving the other section's pending
  // edits intact. The user must still click "Guardar" to persist.
  const restoreRelationshipsToAutodetected = () => {
    if (!draft || !original) return;
    const next = structuredClone(draft);
    next.relationships = structuredClone(original.relationships);
    setDraft(next);
    toast.success("Relaciones restauradas a autodetección (sin guardar)");
  };

  const restoreTypesToAutodetected = () => {
    if (!draft || !original) return;
    const next = structuredClone(draft);
    next.encoding_types = structuredClone(original.encoding_types);
    setDraft(next);
    toast.success("Tipos restaurados a autodetección (sin guardar)");
  };

  // Discard-changes throws away unsaved edits in a section by reverting it
  // to the server's last saved value.
  const discardRelationshipChanges = () => {
    if (!draft || !saved) return;
    const next = structuredClone(draft);
    next.relationships = structuredClone(saved.relationships);
    setDraft(next);
  };

  const discardTypeChanges = () => {
    if (!draft || !saved) return;
    const next = structuredClone(draft);
    next.encoding_types = structuredClone(saved.encoding_types);
    setDraft(next);
  };

  // Catalog of every inspection on the server — powers the history table
  // below. Refreshed whenever the active inspection changes status or a new
  // run is launched.
  const inspectionsQuery = useQuery({
    queryKey: ["inspections"],
    queryFn: async () => {
      const { data } = await api.get<InspectionSummary[]>("/inspections/");
      return data;
    },
  });

  // Quick preview (columns + first rows) for the currently-selected files,
  // so the user can sanity-check what will be inspected before committing.
  // Sorted+joined so identical selection sets reuse the cache.
  const selectedKey = useMemo(
    () => Array.from(selected).sort().join("|"),
    [selected],
  );
  const selectedPreviewQuery = useQuery({
    queryKey: ["files", "preview", "rows", selectedKey],
    enabled: selected.size > 0,
    queryFn: async () => {
      const { data } = await api.post<FilePreview[]>("/files/preview", {
        paths: Array.from(selected),
        sample_rows: 5,
      });
      return data;
    },
  });

  const activeStatus = inspectionQuery.data?.status;
  useEffect(() => {
    if (activeStatus && activeStatus !== "in_progress") {
      queryClient.invalidateQueries({ queryKey: ["inspections"] });
    }
  }, [activeStatus, queryClient]);

  // Silently clear a stale stored ID when the backend can't find it,
  // so the user never sees the "¿El backend está activo?" error on load.
  useEffect(() => {
    if (inspectionQuery.isError && inspectionId) {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  }, [inspectionQuery.isError, inspectionId]);

  const handleReset = () => {
    setInspectionId(null);
    window.localStorage.removeItem(STORAGE_KEY);
  };

  // Profiling reports used to live on a separate page; folded in here so the
  // entire inspection workflow (run → schema → per-table HTML reports) is
  // visible in one place.
  const profilingQuery = useQuery({
    queryKey: ["profiling-reports", inspectionId],
    enabled: !!inspectionId && isCompleted,
    queryFn: async () => {
      const { data } = await api.get<ProfilingReports>(
        `/inspections/${inspectionId}/profiling`,
      );
      return data;
    },
  });

  // POST /files/upload — multipart, one request for all selected files so the
  // backend can reject the batch atomically on conflicts.
  const uploadFiles = useMutation({
    mutationFn: async (fileList: File[]) => {
      const form = new FormData();
      for (const f of fileList) form.append("files", f, f.name);
      const { data } = await api.post<DataFile[]>("/files/upload", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      return data;
    },
    onSuccess: (saved) => {
      toast.success(
        saved.length === 1
          ? `Subido: ${saved[0].name}`
          : `${saved.length} ficheros subidos`,
      );
      queryClient.invalidateQueries({ queryKey: ["files"] });
      queryClient.invalidateQueries({ queryKey: ["upload-stats"] });
      setSourceFilter("uploads");
    },
    onError: (err: unknown) => {
      let detail = "Error desconocido";
      let networkError = false;
      if (axios.isAxiosError(err)) {
        detail =
          (err.response?.data as { detail?: string } | undefined)?.detail ??
          err.message;
        // No response means the request never returned a status (tunnel dropped,
        // proxy timeout, connection reset). The server may still have written
        // the file, so refresh listings instead of leaving a stale view.
        networkError = !err.response;
      } else if (err instanceof Error) {
        detail = err.message;
      }
      if (networkError) {
        queryClient.invalidateQueries({ queryKey: ["files"] });
        queryClient.invalidateQueries({ queryKey: ["upload-stats"] });
        setSourceFilter("uploads");
        toast.warning(
          `Conexión interrumpida (${detail}). Refrescando — el fichero puede haberse subido igualmente.`,
        );
      } else {
        toast.error(`No se pudo subir: ${detail}`);
      }
    },
  });

  const deleteUploads = useMutation({
    mutationFn: async () => {
      const { data } = await api.delete<string[]>("/files/uploads");
      return data;
    },
    onSuccess: (removed) => {
      toast.success(
        removed.length === 0
          ? "No había uploads que borrar"
          : `Borrados ${removed.length} uploads`,
      );
      setSelected((prev) => {
        const next = new Set(prev);
        for (const p of prev) if (p.includes("/uploads/")) next.delete(p);
        return next;
      });
      queryClient.invalidateQueries({ queryKey: ["files"] });
      queryClient.invalidateQueries({ queryKey: ["upload-stats"] });
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Error desconocido";
      toast.error(`No se pudieron borrar los uploads: ${msg}`);
    },
  });

  const deleteInspection = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/inspections/${id}`);
    },
    onSuccess: (_data, id) => {
      toast.success(`Inspección eliminada: ${id}`);
      if (inspectionId === id) {
        setInspectionId(null);
        window.localStorage.removeItem(STORAGE_KEY);
      }
      queryClient.invalidateQueries({ queryKey: ["inspections"] });
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Error desconocido";
      toast.error(`No se pudo eliminar: ${msg}`);
    },
  });

  const renameInspection = useMutation({
    mutationFn: async ({ id, name }: { id: string; name: string }) => {
      await api.patch(`/inspections/${id}/name`, { name });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["inspections"] });
    },
  });

  const cleanupInspections = useMutation({
    mutationFn: async () => {
      const { data } = await api.delete("/inspections/cleanup");
      return data as { deleted_ids: string[] };
    },
    onSuccess: (result) => {
      const n = result.deleted_ids?.length ?? 0;
      toast.success(n > 0 ? `${n} inspección(es) limpiada(s)` : "Nada que limpiar");
      queryClient.invalidateQueries({ queryKey: ["inspections"] });
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Error desconocido";
      toast.error(`Error en limpieza: ${msg}`);
    },
  });

  const purgeInspectionsMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.delete("/inspections/purge");
      return data as { deleted_ids: string[] };
    },
    onSuccess: (result) => {
      const n = result.deleted_ids?.length ?? 0;
      toast.success(`${n} inspección(es) eliminadas`);
      queryClient.invalidateQueries({ queryKey: ["inspections"] });
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Error desconocido";
      toast.error(`Error al purgar: ${msg}`);
    },
  });

  const startInspection = useMutation({
    mutationFn: async (filePaths: string[]) => {
      const { data } = await api.post<InspectionJob>("/inspections/", {
        file_paths: filePaths,
        csv_delimiter: ",",
        enable_data_profiling: enableProfiling,
      });
      return data;
    },
    onSuccess: (job) => {
      window.localStorage.setItem(STORAGE_KEY, job.inspection_id);
      setInspectionId(job.inspection_id);
      toast.success(`Inspección iniciada: ${job.inspection_id}`);
      queryClient.invalidateQueries({ queryKey: ["inspection", job.inspection_id] });
      queryClient.invalidateQueries({ queryKey: ["inspections"] });
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Error desconocido";
      toast.error(`No se pudo iniciar la inspección: ${msg}`);
    },
  });

  const cancelInspection = useMutation({
    mutationFn: async (id: string) => {
      const { data } = await api.post(`/inspections/${id}/cancel`);
      return data;
    },
    onSuccess: (_data, id) => {
      toast.success("Cancelación solicitada");
      queryClient.invalidateQueries({ queryKey: ["inspection", id] });
      queryClient.invalidateQueries({ queryKey: ["inspections"] });
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Error desconocido";
      toast.error(`No se pudo cancelar: ${msg}`);
    },
  });

  const toggleSelected = (path: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const canAdvance = isCompleted;

  const previewContent = useMemo(() => {
    if (!inspectionId) {
      return (
        <p className="text-sm text-muted-foreground">
          Selecciona archivos e inicia la inspección para ver los resultados.
        </p>
      );
    }
    if (inspectionQuery.isLoading) return <Skeleton className="h-24 w-full" />;
    if (inspectionQuery.isError) return null;
    const data = inspectionQuery.data;
    if (!data) return null;
    if (data.status === "in_progress") {
      return (
        <p className="text-sm text-muted-foreground">
          Procesando… Esto puede tardar unos segundos.
        </p>
      );
    }
    if (data.status === "failed") {
      return (
        <p className="text-sm text-destructive">
          La inspección falló. Revisa los logs del backend.
        </p>
      );
    }
    const tables = Object.entries(data.tables ?? {});
    if (tables.length === 0) {
      return (
        <p className="text-sm text-muted-foreground">
          Inspección completada pero sin tablas detectadas.
        </p>
      );
    }
    return (
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Tabla</TableHead>
            <TableHead className="text-right">Filas</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {tables.map(([name, rows]) => (
            <TableRow key={name}>
              <TableCell className="font-mono text-xs">{name}</TableCell>
              <TableCell className="text-right tabular-nums">
                {rows.toLocaleString()}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    );
  }, [inspectionId, inspectionQuery.data, inspectionQuery.isError, inspectionQuery.isLoading]);

  const allFiles = filesQuery.data ?? [];
  const isUpload = (f: DataFile) => f.path.includes("/uploads/");
  // In production (ALLOW_SERVER_FILES=false) the server files tab is hidden
  // and only uploads are shown. In development the user can flip between
  // both with the source filter below.
  const files = !allowServerFiles
    ? allFiles.filter(isUpload)
    : sourceFilter === "uploads"
      ? allFiles.filter(isUpload)
      : allFiles.filter((f) => !isUpload(f));
  const uploadCount = allFiles.filter(isUpload).length;

  const onPickFilesToUpload = () => fileInputRef.current?.click();
  const onFilesPicked = (ev: React.ChangeEvent<HTMLInputElement>) => {
    const picked = Array.from(ev.target.files ?? []);
    if (picked.length > 0) uploadFiles.mutate(picked);
    // Reset the input so the same filename can be re-picked after a conflict
    // rename on the server side.
    ev.target.value = "";
  };

  return (
    <WizardShell currentSlug="inspeccion" canAdvance={canAdvance}>
      <div className="mx-auto max-w-5xl space-y-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Inspección</h1>
            <p className="text-sm text-muted-foreground">
              Selecciona los ficheros ya disponibles en el servidor para
              autodetectar tablas, claves y tipos.
            </p>
          </div>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setRulesOpen(true)}
            >
              <Settings className="mr-2 h-4 w-4" />
              Reglas
            </Button>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <Tabs defaultValue="files" className="w-full">
              <CardHeader className="items-center text-center">
                <TabsList>
                  <TabsTrigger value="files">
                    <Upload className="mr-2 h-4 w-4" />
                    Ficheros
                  </TabsTrigger>
                  <TabsTrigger value="db">
                    <Database className="mr-2 h-4 w-4" />
                    Base de datos
                  </TabsTrigger>
                </TabsList>
              </CardHeader>
              <TabsContent value="files">
                <CardHeader className="items-center pt-0 text-center">
                  <CardTitle>Seleccionar Ficheros</CardTitle>
                  <CardDescription>
                    {allowServerFiles
                      ? "Sube tus propios ficheros o usa los disponibles en backend/data/."
                      : "Sube los ficheros que quieras inspeccionar."}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept=".csv,.parquet,.json"
                    className="hidden"
                    onChange={onFilesPicked}
                  />

                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      type="button"
                      size="sm"
                      variant="default"
                      onClick={onPickFilesToUpload}
                      disabled={
                        uploadFiles.isPending ||
                        (uploadStatsQuery.data
                          ? uploadStatsQuery.data.used_bytes >= uploadStatsQuery.data.limit_bytes
                          : false)
                      }
                    >
                      <Upload className="mr-2 h-4 w-4" />
                      {uploadFiles.isPending ? "Subiendo…" : "Subir ficheros"}
                    </Button>
                    {uploadCount > 0 && (
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => deleteUploads.mutate()}
                        disabled={deleteUploads.isPending}
                      >
                        <Trash2 className="mr-2 h-4 w-4" />
                        Borrar uploads ({uploadCount})
                      </Button>
                    )}
                  </div>

                  <UploadStorageBar stats={uploadStatsQuery.data} />

                  {allowServerFiles && (
                    <div className="flex flex-wrap gap-2">
                      {(
                        [
                          ["uploads", `Subidos (${uploadCount})`],
                          ["server", "Del servidor"],
                        ] as const
                      ).map(([value, label]) => (
                        <button
                          key={value}
                          type="button"
                          onClick={() => setSourceFilter(value)}
                          className={
                            "rounded-full border px-3 py-1 text-xs transition-colors " +
                            (sourceFilter === value
                              ? "border-primary bg-primary/10 text-primary"
                              : "border-muted bg-background text-muted-foreground hover:bg-accent")
                          }
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  )}

                  <div className="flex flex-wrap gap-2">
                    {(["all", ...EXT_FILTERS] as const).map((e) => (
                      <button
                        key={e}
                        type="button"
                        onClick={() => setExtFilter(e)}
                        className={
                          "rounded-full border px-3 py-1 text-xs transition-colors " +
                          (extFilter === e
                            ? "border-primary bg-primary/10 text-primary"
                            : "border-muted bg-background text-muted-foreground hover:bg-accent")
                        }
                      >
                        {e === "all" ? "todos" : e}
                      </button>
                    ))}
                  </div>

                  <div className="max-h-64 overflow-auto rounded-md border">
                    {filesQuery.isLoading && (
                      <div className="space-y-2 p-3">
                        <Skeleton className="h-6 w-full" />
                        <Skeleton className="h-6 w-full" />
                      </div>
                    )}
                    {filesQuery.isError && (
                      <p className="p-3 text-sm text-destructive">
                        No se pudo cargar la lista de ficheros.
                      </p>
                    )}
                    {filesQuery.data && files.length === 0 && (
                      <p className="p-3 text-sm text-muted-foreground">
                        {allowServerFiles && sourceFilter === "server"
                          ? "No hay ficheros del servidor en backend/data/."
                          : "Aún no has subido ningún fichero. Pulsa \"Subir ficheros\"."}
                      </p>
                    )}
                    <ul className="divide-y">
                      {files.map((f) => {
                        const isSel = selected.has(f.path);
                        return (
                          <li key={f.path}>
                            <button
                              type="button"
                              onClick={() => toggleSelected(f.path)}
                              className={
                                "flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm transition-colors " +
                                (isSel ? "bg-primary/5" : "hover:bg-accent")
                              }
                            >
                              <div className="flex min-w-0 items-center gap-3">
                                <input
                                  type="checkbox"
                                  checked={isSel}
                                  readOnly
                                  className="h-4 w-4"
                                />
                                <span className="truncate font-medium">{f.name}</span>
                              </div>
                              <div className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
                                <span>{formatSize(f.size_bytes)}</span>
                                <Badge variant="secondary" className="uppercase">
                                  {f.extension}
                                </Badge>
                              </div>
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  </div>

                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      className="h-4 w-4"
                      checked={enableProfiling}
                      onChange={(e) => setEnableProfiling(e.target.checked)}
                    />
                    <span>Generar informes de profiling (ydata-profiling)</span>
                  </label>

                  <Button
                    type="button"
                    className="w-full"
                    disabled={selected.size === 0 || startInspection.isPending}
                    onClick={() => startInspection.mutate(Array.from(selected))}
                  >
                    {startInspection.isPending
                      ? "Iniciando…"
                      : `Iniciar Inspección (${selected.size})`}
                  </Button>
                </CardContent>
              </TabsContent>

              <TabsContent value="db">
                <CardHeader className="items-center pt-0 text-center opacity-75">
                  <CardTitle>Base de Datos Externa</CardTitle>
                  <CardDescription>Próximamente.</CardDescription>
                </CardHeader>
                <CardContent className="text-center">
                  <Button variant="outline" disabled>
                    Configurar Conexión — Próximamente
                  </Button>
                </CardContent>
              </TabsContent>
            </Tabs>
          </Card>

          <InspectionStatusCard
            inspectionId={inspectionId}
            inspection={inspectionQuery.data}
            isLoading={inspectionQuery.isLoading}
            isError={inspectionQuery.isError}
          />
        </div>

        {selected.size > 0 && (
          <SelectionPreviewCard
            previews={selectedPreviewQuery.data ?? []}
            isLoading={selectedPreviewQuery.isLoading}
            isError={selectedPreviewQuery.isError}
          />
        )}

        <Card>
          <CardHeader className="flex-row items-start justify-between space-y-0">
            <div>
              <CardTitle className="text-base">Tablas Detectadas</CardTitle>
              <CardDescription>
                Resumen de tablas y nº de filas tras la inspección.
                {inspectionId && (
                  <span
                    className="ml-2 font-mono text-xs"
                    suppressHydrationWarning
                  >
                    id: {inspectionId}
                  </span>
                )}
              </CardDescription>
              {inspectionId && (() => {
                const active = (inspectionsQuery.data ?? []).find(
                  (x) => x.inspection_id === inspectionId,
                );
                if (!active) return null;
                return (
                  <EditableName
                    name={active.inspection_name || active.inspection_id}
                    existingNames={(inspectionsQuery.data ?? []).map(
                      (x) => x.inspection_name || x.inspection_id,
                    )}
                    onSave={(name) =>
                      renameInspection.mutateAsync({ id: inspectionId, name })
                    }
                  />
                );
              })()}
            </div>
            {inspectionId && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={handleReset}
              >
                Nueva inspección
              </Button>
            )}
          </CardHeader>
          <CardContent>{previewContent}</CardContent>
        </Card>

        {isCompleted && (
          <>
            <RelationshipsCard
              query={autodetectQuery}
              draft={draft}
              setDraft={setDraft}
              dirtyVsSaved={relsDirtyVsSaved}
              differsFromOriginal={relsDiffersFromOriginal}
              originalAvailable={!!original}
              onSave={saveRelationships}
              onRestoreAutodetected={restoreRelationshipsToAutodetected}
              onDiscardChanges={discardRelationshipChanges}
              isSaving={saveRelationshipsMutation.isPending}
            />
            <TypesCard
              query={autodetectQuery}
              draft={draft}
              setDraft={setDraft}
              dirtyVsSaved={typesDirtyVsSaved}
              differsFromOriginal={typesDiffersFromOriginal}
              originalAvailable={!!original}
              onSave={saveTypes}
              onRestoreAutodetected={restoreTypesToAutodetected}
              onDiscardChanges={discardTypeChanges}
              isSaving={saveTypesMutation.isPending}
            />
            <ProfilingCard
              inspectionId={inspectionId}
              query={profilingQuery}
            />
          </>
        )}

        <HistoryCard
          inspections={inspectionsQuery.data ?? []}
          isLoading={inspectionsQuery.isLoading}
          isError={inspectionsQuery.isError}
          activeId={inspectionId}
          onSelect={(id) => {
            window.localStorage.setItem(STORAGE_KEY, id);
            setInspectionId(id);
          }}
          onDelete={(id) => setConfirmDelete(id)}
          onRename={(id, name) => renameInspection.mutateAsync({ id, name })}
          onCleanup={() => setConfirmCleanup(true)}
          onPurge={() => setConfirmPurge(true)}
          onCancel={(id) => cancelInspection.mutate(id)}
          isDeleting={deleteInspection.isPending}
          isCleaning={cleanupInspections.isPending}
          isPurging={purgeInspectionsMutation.isPending}
          isCancelling={cancelInspection.isPending}
        />

        <ConfirmDialog
          open={confirmDelete !== null}
          title="¿Eliminar inspección?"
          description="Se borrarán permanentemente la carpeta y todos sus artefactos (metadatos, profiling, etc.). Esta acción no se puede deshacer."
          confirmLabel="Eliminar"
          onConfirm={() => {
            if (confirmDelete) deleteInspection.mutate(confirmDelete);
            setConfirmDelete(null);
          }}
          onCancel={() => setConfirmDelete(null)}
        />
        <RulesEditor
          open={rulesOpen}
          onClose={() => setRulesOpen(false)}
          autodetect={autodetectQuery.data ?? null}
          pendingFilePaths={Array.from(selected)}
        />

        <ConfirmDialog
          open={confirmPurge}
          title="¿Purgar todas las inspecciones?"
          description="Se eliminarán TODAS las inspecciones, incluidas las completadas correctamente. Esta acción no se puede deshacer."
          confirmLabel="Purgar"
          onConfirm={() => {
            purgeInspectionsMutation.mutate();
            setConfirmPurge(false);
          }}
          onCancel={() => setConfirmPurge(false)}
        />

        <ConfirmDialog
          open={confirmCleanup}
          title="¿Limpiar inspecciones?"
          description="Se borrarán permanentemente las carpetas vacías, las ejecuciones huérfanas y los duplicados exactos (mismos ficheros, ejecución más antigua). Esta acción no se puede deshacer."
          confirmLabel="Limpiar"
          onConfirm={() => {
            cleanupInspections.mutate();
            setConfirmCleanup(false);
          }}
          onCancel={() => setConfirmCleanup(false)}
        />
      </div>
    </WizardShell>
  );
}

// ---- Autodetect editor ----
// Edits are kept in a local `draft` lifted to the page so the relationships
// and types cards share the same source of truth. The draft is PUT to the
// backend on save; "Restaurar" pulls the pristine snapshot from
// /autodetect/original.

type AutodetectQuery = {
  data: Autodetect | undefined;
  isLoading: boolean;
  isError: boolean;
};

const SELECT_CLASS =
  "rounded-md border bg-background px-2 py-1 font-mono text-xs focus:outline-none focus:ring-1 focus:ring-ring";

function RelationshipsCard({
  query,
  draft,
  setDraft,
  dirtyVsSaved,
  differsFromOriginal,
  originalAvailable,
  onSave,
  onRestoreAutodetected,
  onDiscardChanges,
  isSaving,
}: {
  query: AutodetectQuery;
  draft: Autodetect | null;
  setDraft: (value: Autodetect | null) => void;
  dirtyVsSaved: boolean;
  differsFromOriginal: boolean;
  originalAvailable: boolean;
  onSave: () => void;
  onRestoreAutodetected: () => void;
  onDiscardChanges: () => void;
  isSaving: boolean;
}) {
  const tables = useMemo(
    () => (draft ? Object.keys(draft.encoding_types) : []),
    [draft],
  );

  const columnsByTable = (table: string): string[] =>
    draft ? Object.keys(draft.encoding_types[table] ?? {}) : [];

  const updatePk = (table: string, column: string) => {
    if (!draft) return;
    const next = structuredClone(draft);
    if (column === "") {
      delete next.relationships.pks[table];
    } else {
      next.relationships.pks[table] = column;
    }
    setDraft(next);
  };

  const updateFk = (index: number, patch: Partial<ForeignKey>) => {
    if (!draft) return;
    const next = structuredClone(draft);
    const updated = { ...next.relationships.fks[index], ...patch };
    next.relationships.fks[index] = updated;
    // MostlyAI accepts at most one context FK per child table. Toggling
    // context on for a row clears the flag on every other row with the same
    // child so the user never has to remember the constraint.
    if (patch.is_context === true) {
      next.relationships.fks.forEach((fk, i) => {
        if (i !== index && fk.child === updated.child && fk.is_context) {
          fk.is_context = false;
        }
      });
    }
    setDraft(next);
  };

  const removeFk = (index: number) => {
    if (!draft) return;
    const next = structuredClone(draft);
    next.relationships.fks.splice(index, 1);
    setDraft(next);
  };

  const addFk = () => {
    if (!draft || tables.length === 0) return;
    const next = structuredClone(draft);
    const parent = tables[0];
    const child = tables[tables.length > 1 ? 1 : 0];
    const pkCol = next.relationships.pks[parent] ?? columnsByTable(parent)[0] ?? "";
    const fkCol = columnsByTable(child)[0] ?? "";
    next.relationships.fks.push({
      parent,
      child,
      fk_column: fkCol,
      pk_column: pkCol,
      is_context: false,
    });
    setDraft(next);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Relaciones Detectadas</CardTitle>
        <CardDescription>
          Edita claves primarias y relaciones entre tablas. Los cambios solo se
          aplican al guardar.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {query.isLoading && <Skeleton className="h-24 w-full" />}
        {query.isError && (
          <p className="text-sm text-destructive">
            No se pudo cargar autodetect.json.
          </p>
        )}
        {draft && (
          <>
            <div>
              <h3 className="mb-2 text-sm font-medium">Diagrama</h3>
              <RelationshipsGraph autodetect={draft} />
            </div>

            <div className="flex flex-wrap items-center justify-end gap-2 rounded-md border bg-muted/40 px-3 py-2">
              <span className="mr-auto text-xs text-muted-foreground">
                {dirtyVsSaved
                  ? "Hay cambios sin guardar en relaciones."
                  : differsFromOriginal
                    ? "Relaciones modificadas respecto a la autodetección."
                    : "Relaciones sincronizadas con la autodetección."}
              </span>
              {differsFromOriginal && originalAvailable && (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={onRestoreAutodetected}
                >
                  Restaurar autodetectado
                </Button>
              )}
              {dirtyVsSaved && (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={onDiscardChanges}
                >
                  Descartar cambios
                </Button>
              )}
              <Button
                type="button"
                size="sm"
                onClick={onSave}
                disabled={!dirtyVsSaved || isSaving}
              >
                {isSaving ? "Guardando…" : "Guardar relaciones"}
              </Button>
            </div>

            <div>
              <h3 className="mb-2 text-sm font-medium">Claves primarias</h3>
              {tables.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No hay tablas para configurar.
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Tabla</TableHead>
                      <TableHead>Columna PK</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {tables.map((table) => (
                      <TableRow key={table}>
                        <TableCell className="font-mono text-xs">{table}</TableCell>
                        <TableCell>
                          <select
                            className={SELECT_CLASS}
                            value={draft.relationships.pks[table] ?? ""}
                            onChange={(e) => updatePk(table, e.target.value)}
                          >
                            <option value="">— sin PK —</option>
                            {columnsByTable(table).map((c) => (
                              <option key={c} value={c}>
                                {c}
                              </option>
                            ))}
                          </select>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </div>

            <div>
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-sm font-medium">Claves foráneas</h3>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={addFk}
                  disabled={tables.length === 0}
                >
                  Añadir relación
                </Button>
              </div>
              {draft.relationships.fks.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No hay relaciones definidas.
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Tabla Padre</TableHead>
                      <TableHead>Tabla Hija</TableHead>
                      <TableHead>Columna Padre (PK)</TableHead>
                      <TableHead>Columna FK Hija</TableHead>
                      <TableHead>Contexto</TableHead>
                      <TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {draft.relationships.fks.map((fk, i) => (
                      <TableRow key={i}>
                        <TableCell>
                          <select
                            className={SELECT_CLASS}
                            value={fk.parent}
                            onChange={(e) =>
                              updateFk(i, { parent: e.target.value })
                            }
                          >
                            {tables.map((t) => (
                              <option key={t} value={t}>
                                {t}
                              </option>
                            ))}
                          </select>
                        </TableCell>
                        <TableCell>
                          <select
                            className={SELECT_CLASS}
                            value={fk.child}
                            onChange={(e) =>
                              updateFk(i, { child: e.target.value })
                            }
                          >
                            {tables.map((t) => (
                              <option key={t} value={t}>
                                {t}
                              </option>
                            ))}
                          </select>
                        </TableCell>
                        <TableCell>
                          <select
                            className={SELECT_CLASS}
                            value={fk.pk_column}
                            onChange={(e) =>
                              updateFk(i, { pk_column: e.target.value })
                            }
                          >
                            {columnsByTable(fk.parent).map((c) => (
                              <option key={c} value={c}>
                                {c}
                              </option>
                            ))}
                          </select>
                        </TableCell>
                        <TableCell>
                          <select
                            className={SELECT_CLASS}
                            value={fk.fk_column}
                            onChange={(e) =>
                              updateFk(i, { fk_column: e.target.value })
                            }
                          >
                            {columnsByTable(fk.child).map((c) => (
                              <option key={c} value={c}>
                                {c}
                              </option>
                            ))}
                          </select>
                        </TableCell>
                        <TableCell>
                          <input
                            type="checkbox"
                            className="h-4 w-4"
                            checked={fk.is_context}
                            onChange={(e) =>
                              updateFk(i, { is_context: e.target.checked })
                            }
                          />
                        </TableCell>
                        <TableCell className="text-right">
                          <button
                            type="button"
                            aria-label="Eliminar relación"
                            onClick={() => removeFk(i)}
                            className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function statusBadgeVariant(
  status: string,
): "default" | "secondary" | "outline" | "destructive" {
  if (status === "completed") return "default";
  if (status === "in_progress") return "secondary";
  if (status === "failed" || status === "cancelled") return "destructive";
  return "outline";
}

function HistoryCard({
  inspections,
  isLoading,
  isError,
  activeId,
  onSelect,
  onDelete,
  onRename,
  onCleanup,
  onPurge,
  onCancel,
  isDeleting,
  isCleaning,
  isPurging,
  isCancelling,
}: {
  inspections: InspectionSummary[];
  isLoading: boolean;
  isError: boolean;
  activeId: string | null;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onRename: (id: string, name: string) => Promise<void>;
  onCleanup: () => void;
  onPurge: () => void;
  onCancel: (id: string) => void;
  isDeleting: boolean;
  isCleaning: boolean;
  isPurging: boolean;
  isCancelling: boolean;
}) {
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between space-y-0">
        <div>
          <CardTitle className="text-base">Inspecciones previas</CardTitle>
          <CardDescription>
            Catálogo completo de inspecciones del servidor. Haz click para cargar
            una inspección pasada y ver su esquema y profiling.
          </CardDescription>
        </div>
        <div className="flex gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={isCleaning || inspections.length === 0}
            onClick={onCleanup}
          >
            <Trash2 className="mr-2 h-3.5 w-3.5" />
            Limpiar sesiones incompletas
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={isPurging || inspections.length === 0}
            onClick={onPurge}
          >
            <Trash2 className="mr-2 h-3.5 w-3.5" />
            Limpiar todas las sesiones
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading && <Skeleton className="h-24 w-full" />}
        {isError && (
          <p className="text-sm text-destructive">
            No se pudo cargar el catálogo de inspecciones.
          </p>
        )}
        {!isLoading && !isError && inspections.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Todavía no hay inspecciones.
          </p>
        )}
        {inspections.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nombre</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead>Tablas</TableHead>
                <TableHead className="text-right">Filas</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {inspections.map((i) => {
                const isActive = i.inspection_id === activeId;
                const tableNames = Object.keys(i.tables ?? {});
                const totalRows = Object.values(i.tables ?? {}).reduce(
                  (a, b) => a + b,
                  0,
                );
                const allNames = inspections.map(
                  (x) => x.inspection_name || x.inspection_id,
                );
                return (
                  <TableRow
                    key={i.inspection_id}
                    onClick={() => onSelect(i.inspection_id)}
                    className={
                      "cursor-pointer " +
                      (isActive ? "bg-primary/5" : "hover:bg-accent")
                    }
                  >
                    <TableCell>
                      <div className="space-y-0.5">
                        <p className="font-mono text-[10px] text-muted-foreground">
                          {i.inspection_id}
                        </p>
                        <EditableName
                          name={i.inspection_name || i.inspection_id}
                          existingNames={allNames}
                          onSave={(name) => onRename(i.inspection_id, name)}
                        />
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant={statusBadgeVariant(i.status)}>
                        {i.status || "—"}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {tableNames.length > 0 ? tableNames.join(", ") : "—"}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {totalRows > 0 ? totalRows.toLocaleString() : "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      {i.status === "in_progress" ? (
                        <button
                          type="button"
                          aria-label="Cancelar inspección"
                          disabled={isCancelling}
                          onClick={(e) => {
                            e.stopPropagation();
                            onCancel(i.inspection_id);
                          }}
                          className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-40"
                        >
                          <XCircle className="h-3.5 w-3.5" />
                        </button>
                      ) : (
                        <button
                          type="button"
                          aria-label="Eliminar inspección"
                          disabled={isDeleting}
                          onClick={(e) => {
                            e.stopPropagation();
                            onDelete(i.inspection_id);
                          }}
                          className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-40"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

function ProfilingCard({
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
        <div>
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

function TypesCard({
  query,
  draft,
  setDraft,
  dirtyVsSaved,
  differsFromOriginal,
  originalAvailable,
  onSave,
  onRestoreAutodetected,
  onDiscardChanges,
  isSaving,
}: {
  query: AutodetectQuery;
  draft: Autodetect | null;
  setDraft: (value: Autodetect | null) => void;
  dirtyVsSaved: boolean;
  differsFromOriginal: boolean;
  originalAvailable: boolean;
  onSave: () => void;
  onRestoreAutodetected: () => void;
  onDiscardChanges: () => void;
  isSaving: boolean;
}) {
  const updateType = (table: string, column: string, type: string) => {
    if (!draft) return;
    const next = structuredClone(draft);
    next.encoding_types[table][column] = type;
    setDraft(next);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Tipos de Codificación</CardTitle>
        <CardDescription>
          Edita el tipo MostlyAI de cada columna. Guarda los cambios desde el
          panel de relaciones.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {query.isLoading && <Skeleton className="h-24 w-full" />}
        {query.isError && (
          <p className="text-sm text-destructive">
            No se pudo cargar autodetect.json.
          </p>
        )}
        {draft && (
          <div className="flex flex-wrap items-center justify-end gap-2 rounded-md border bg-muted/40 px-3 py-2">
            <span className="mr-auto text-xs text-muted-foreground">
              {dirtyVsSaved
                ? "Hay cambios sin guardar en tipos."
                : differsFromOriginal
                  ? "Tipos modificados respecto a la autodetección."
                  : "Tipos sincronizados con la autodetección."}
            </span>
            {differsFromOriginal && originalAvailable && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={onRestoreAutodetected}
              >
                Restaurar autodetectado
              </Button>
            )}
            {dirtyVsSaved && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={onDiscardChanges}
              >
                Descartar cambios
              </Button>
            )}
            <Button
              type="button"
              size="sm"
              onClick={onSave}
              disabled={!dirtyVsSaved || isSaving}
            >
              {isSaving ? "Guardando…" : "Guardar tipos"}
            </Button>
          </div>
        )}
        {draft &&
          Object.entries(draft.encoding_types).map(([table, columns]) => (
            <div key={table}>
              <h3 className="mb-2 font-mono text-sm font-medium">{table}</h3>
              <div className="flex flex-wrap gap-2">
                {Object.entries(columns).map(([col, type]) => (
                  <label
                    key={col}
                    className="flex items-center gap-2 rounded-md border bg-card px-2 py-1 text-xs"
                  >
                    <span className="font-mono">{col}</span>
                    <select
                      value={type}
                      onChange={(e) => updateType(table, col, e.target.value)}
                      className={
                        "rounded border px-1.5 py-0.5 text-[10px] font-medium focus:outline-none focus:ring-1 focus:ring-ring " +
                        typeBadgeClass(type)
                      }
                    >
                      {ENCODING_TYPES.map((t) => (
                        <option key={t} value={t}>
                          {t.replace("TABULAR_", "")}
                        </option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
            </div>
          ))}
      </CardContent>
    </Card>
  );
}

function SelectionPreviewCard({
  previews,
  isLoading,
  isError,
}: {
  previews: FilePreview[];
  isLoading: boolean;
  isError: boolean;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Vista previa de la selección</CardTitle>
        <CardDescription>
          Cabecera y primeras filas de los ficheros seleccionados, antes de
          inspeccionar.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {isLoading && <Skeleton className="h-24 w-full" />}
        {isError && (
          <p className="text-sm text-destructive">
            No se pudo cargar la vista previa.
          </p>
        )}
        {!isLoading &&
          !isError &&
          previews.map((p) => (
            <div key={p.path}>
              <div className="mb-2 flex items-baseline justify-between gap-2">
                <h3 className="font-mono text-sm font-medium">{p.table}</h3>
                <span className="text-xs text-muted-foreground">
                  {p.columns.length} columnas
                </span>
              </div>
              <div className="overflow-auto rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      {p.columns.map((c) => (
                        <TableHead key={c} className="font-mono text-xs">
                          {c}
                        </TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {p.rows.length === 0 ? (
                      <TableRow>
                        <TableCell
                          colSpan={Math.max(1, p.columns.length)}
                          className="text-xs text-muted-foreground"
                        >
                          Sin filas para mostrar.
                        </TableCell>
                      </TableRow>
                    ) : (
                      p.rows.map((row, i) => (
                        <TableRow key={i}>
                          {p.columns.map((_, j) => (
                            <TableCell
                              key={j}
                              className="truncate font-mono text-xs max-w-[200px]"
                            >
                              {row[j] ?? ""}
                            </TableCell>
                          ))}
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </div>
          ))}
      </CardContent>
    </Card>
  );
}

function InspectionStatusCard({
  inspectionId,
  inspection,
  isLoading,
  isError,
}: {
  inspectionId: string | null;
  inspection: InspectionSummary | undefined;
  isLoading: boolean;
  isError: boolean;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Inspección actual</CardTitle>
        <CardDescription>
          Estado de la inspección activa en esta sesión.
          {inspectionId && (
            <span
              className="ml-2 font-mono text-xs"
              suppressHydrationWarning
            >
              id: {inspectionId}
            </span>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {!inspectionId && (
          <p className="text-sm text-muted-foreground">
            Aún no has iniciado una inspección en esta sesión.
          </p>
        )}
        {inspectionId && isLoading && <Skeleton className="h-20 w-full" />}
        {inspectionId && isError && (
          <p className="text-sm text-destructive">
            No se pudo cargar el estado de la inspección.
          </p>
        )}
        {inspection && (
          <div className="space-y-3 text-sm">
            <JobProgressPanel
              status={inspection.status}
              progress={inspection.progress}
              timestamp={inspection.timestamp}
            />
            {inspection.file_paths.length > 0 && (
              <p className="text-xs text-muted-foreground">
                {inspection.file_paths.length} fichero(s) en la inspección.
              </p>
            )}
            {inspection.status === "completed" &&
              Object.keys(inspection.tables ?? {}).length > 0 && (
                <p className="text-xs">
                  <span className="text-muted-foreground">Tablas: </span>
                  <span className="font-mono">
                    {Object.keys(inspection.tables).join(", ")}
                  </span>
                </p>
              )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
