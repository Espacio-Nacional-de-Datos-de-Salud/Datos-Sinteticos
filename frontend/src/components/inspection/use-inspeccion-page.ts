"use client";

// Data-layer hook for the Inspección page. Owns every TanStack query and
// mutation tied to the active inspection, the editable autodetect draft, and
// the dirty/diff memos that drive the save & restore buttons. The page
// component reduces to UI state (selected files, filters, dialogs) plus
// layout that wires this hook into the cards under @/components/inspection.

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  api,
  type Autodetect,
  type InspectionJob,
  type InspectionSummary,
  type ProfilingReports,
} from "@/lib/api";
import { extractDeleteConflict, extractDetail } from "@/lib/errors";
import { STORAGE_KEYS } from "@/lib/storage-keys";
import type {
  DeleteConflictState,
  DeleteMode,
} from "@/components/pipeline-step/use-artifact-lifecycle";

// A cascade delete of an inspection can also remove downstream models,
// simulations, and evaluations, so a successful delete refreshes every list.
const ALL_LIST_KEYS = ["inspections", "models", "simulations", "evaluations"];

const STORAGE_KEY = STORAGE_KEYS.inspection;

export type StartInspectionPayload = {
  filePaths: string[];
  enableProfiling: boolean;
  csvDelimiter: string;
  excludedColumns: Record<string, string[]>;
  /** Optional functional name entered in the start dialog. */
  name?: string;
};

export function useInspeccionPage() {
  const queryClient = useQueryClient();

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

  // Autodetect + pristine snapshot only exist once the run has completed;
  // gate the queries on that to avoid 404 noise during in-progress polling.
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

  // Immediate, destructive column exclusion — calls the dedicated backend
  // endpoint that updates BOTH the schema and the cached parquet files so
  // training never sees the dropped columns.
  const excludeColumnsMutation = useMutation({
    mutationFn: async (payload: Record<string, string[]>) => {
      const { data } = await api.put<Autodetect>(
        `/inspections/${inspectionId}/autodetect/excluded-columns`,
        { excluded_columns: payload },
      );
      return data;
    },
    onSuccess: (data) => {
      toast.success("Columna(s) excluida(s) y datos caché actualizados.");
      queryClient.setQueryData(["autodetect", inspectionId], data);
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Error desconocido";
      toast.error(`No se pudo excluir la columna: ${msg}`);
    },
  });

  // Non-destructive training-time exclusion (used by the auto-flagged-column
  // toggle). Unlike excludeColumnsMutation it never drops the cached data, so a
  // column can be opted back in.
  const trainingExclusionMutation = useMutation({
    mutationFn: async (payload: Record<string, string[]>) => {
      const { data } = await api.put<Autodetect>(
        `/inspections/${inspectionId}/autodetect/training-exclusions`,
        { excluded_columns: payload },
      );
      return data;
    },
    onSuccess: (data) => {
      queryClient.setQueryData(["autodetect", inspectionId], data);
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Error desconocido";
      toast.error(`No se pudo actualizar la exclusión: ${msg}`);
    },
  });

  const toggleTrainingExclusion = (table: string, col: string, excluded: boolean) => {
    if (!draft) return;
    const current: Record<string, string[]> = { ...(draft.excluded_columns ?? {}) };
    const set = new Set(current[table] ?? []);
    if (excluded) set.add(col);
    else set.delete(col);
    if (set.size > 0) current[table] = [...set];
    else delete current[table];
    trainingExclusionMutation.mutate(current);
  };

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

  // ---- Inspections catalogue + lifecycle mutations -------------------------

  const inspectionsQuery = useQuery({
    queryKey: ["inspections"],
    queryFn: async () => {
      const { data } = await api.get<InspectionSummary[]>("/inspections/");
      return data;
    },
  });

  // Whenever the active run changes status we need the catalogue to mirror
  // it so the history card reflects "in_progress" → "completed" without a
  // manual refresh.
  const activeStatus = inspectionQuery.data?.status;
  useEffect(() => {
    if (activeStatus && activeStatus !== "in_progress") {
      queryClient.invalidateQueries({ queryKey: ["inspections"] });
    }
  }, [activeStatus, queryClient]);

  // Silently clear a stale stored ID when the backend can't find it, so the
  // user never sees the "¿El backend está activo?" error on load.
  useEffect(() => {
    if (inspectionQuery.isError && inspectionId) {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  }, [inspectionQuery.isError, inspectionId]);

  const [deleteConflict, setDeleteConflict] =
    useState<DeleteConflictState | null>(null);

  const deleteInspection = useMutation({
    mutationFn: async ({ id, mode }: { id: string; mode: DeleteMode }) => {
      await api.delete(`/inspections/${id}`, {
        params: mode === "safe" ? undefined : { mode },
      });
    },
    onSuccess: (_data, { id }) => {
      toast.success(`Inspección eliminada: ${id}`);
      setDeleteConflict(null);
      if (inspectionId === id) {
        setInspectionId(null);
        window.localStorage.removeItem(STORAGE_KEY);
      }
      for (const key of ALL_LIST_KEYS) {
        queryClient.invalidateQueries({ queryKey: [key] });
      }
    },
    onError: (err, { id, mode }) => {
      const conflict = mode === "safe" ? extractDeleteConflict(err) : null;
      if (conflict) {
        setDeleteConflict({
          id,
          message: conflict.message,
          linkedCount: conflict.linkedIds.length,
        });
        return;
      }
      toast.error(`No se pudo eliminar: ${extractDetail(err)}`);
    },
  });

  const renameInspection = useMutation({
    mutationFn: async ({ id, name }: { id: string; name: string }) => {
      await api.patch(`/inspections/${id}/name`, { name });
    },
    onSuccess: (_data, { id }) => {
      queryClient.invalidateQueries({ queryKey: ["inspections"] });
      queryClient.invalidateQueries({ queryKey: ["inspection", id] });
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

  const purgeInspections = useMutation({
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
    mutationFn: async (payload: StartInspectionPayload) => {
      const trimmedName = payload.name?.trim();
      const { data } = await api.post<InspectionJob>("/inspections/", {
        file_paths: payload.filePaths,
        csv_delimiter: payload.csvDelimiter,
        enable_data_profiling: payload.enableProfiling,
        excluded_columns: payload.excludedColumns,
        ...(trimmedName ? { name: trimmedName } : {}),
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

  const resetActive = () => {
    setInspectionId(null);
    window.localStorage.removeItem(STORAGE_KEY);
  };

  const selectActive = (id: string) => {
    window.localStorage.setItem(STORAGE_KEY, id);
    setInspectionId(id);
  };

  return {
    inspectionId,
    selectActive,
    resetActive,

    inspectionQuery,
    isCompleted,
    autodetectQuery,
    profilingQuery,
    inspectionsQuery,

    draft,
    setDraft,

    relationships: {
      dirtyVsSaved: relsDirtyVsSaved,
      differsFromOriginal: relsDiffersFromOriginal,
      onSave: saveRelationships,
      onRestoreAutodetected: restoreRelationshipsToAutodetected,
      onDiscardChanges: discardRelationshipChanges,
      isSaving: saveRelationshipsMutation.isPending,
    },
    types: {
      dirtyVsSaved: typesDirtyVsSaved,
      differsFromOriginal: typesDiffersFromOriginal,
      onSave: saveTypes,
      onRestoreAutodetected: restoreTypesToAutodetected,
      onDiscardChanges: discardTypeChanges,
      isSaving: saveTypesMutation.isPending,
      onExcludeColumn: (table: string, col: string) =>
        excludeColumnsMutation.mutate({ [table]: [col] }),
      isExcluding: excludeColumnsMutation.isPending,
      onToggleTrainingExclusion: toggleTrainingExclusion,
      isTogglingExclusion: trainingExclusionMutation.isPending,
    },
    originalAvailable: !!original,

    startInspection: (payload: StartInspectionPayload) =>
      startInspection.mutate(payload),
    isStarting: startInspection.isPending,

    deleteInspection: (id: string) =>
      deleteInspection.mutate({ id, mode: "safe" }),
    isDeleting: deleteInspection.isPending,
    deleteConflict,
    dismissDeleteConflict: () => setDeleteConflict(null),
    resolveDeleteConflict: (mode: "force" | "cascade") => {
      if (deleteConflict)
        deleteInspection.mutate({ id: deleteConflict.id, mode });
    },

    renameInspection: (id: string, name: string) =>
      renameInspection.mutateAsync({ id, name }),

    cleanupInspections: () => cleanupInspections.mutate(),
    isCleaning: cleanupInspections.isPending,

    purgeInspections: () => purgeInspections.mutate(),
    isPurging: purgeInspections.isPending,

    cancelInspection: (id: string) => cancelInspection.mutate(id),
    isCancelling: cancelInspection.isPending,
  };
}
