"use client";

// Generic lifecycle hook for the three pipeline-step pages (training,
// simulation, evaluation). Each page deals with a CRUD-ish resource that
// follows the same pattern: a catalogue list, an "active" entry kept in
// localStorage and polled while in_progress, plus start/cancel/delete/
// cleanup/purge/rename mutations. The differences are pure data:
//   • REST path (`/models`, `/simulations`, `/evaluations`)
//   • Cache key noun (singular for the active entry, plural for the list)
//   • Item type (ModelSummary / SimulationSummary / EvaluationSummary)
//   • Start-body shape (driven by the page's form fields)
//   • Toast wording (different Spanish nouns and genders)
//
// Returning everything from one hook keeps the page wiring trivial:
//   const lc = useArtifactLifecycle<ModelSummary, { inspection_id }>({...})
//   lc.start({ inspection_id })   // POST /models/
//   lc.cancel(id)                 // POST /models/{id}/cancel
//   lc.completedList              // list filtered to status==="completed"

import { useEffect, useMemo, useState } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { extractDetail } from "@/lib/errors";

export type ArtifactStatus =
  | "in_progress"
  | "completed"
  | "failed"
  | "cancelled"
  | (string & {});

export interface ArtifactItem {
  status: ArtifactStatus;
}

export type ArtifactLifecycleLabels = {
  /** Toast on successful start. Receives the new artifact id. */
  startedToast: (id: string) => string;
  /** Toast prefix for start failures; the API detail is appended. */
  startErrorPrefix: string;
  /** Toast prefix for cancel failures. */
  cancelErrorPrefix: string;
  /** Toast on successful delete (one item). */
  deletedToast: (id: string) => string;
  /** Toast prefix for delete failures. */
  deleteErrorPrefix: string;
  /** Toast on successful cleanup with N≥1 deleted ids. */
  cleanupOkToast: (n: number) => string;
  /** Toast when cleanup deleted nothing (N==0). */
  cleanupNoopToast: string;
  /** Toast prefix for cleanup failures. */
  cleanupErrorPrefix: string;
  /** Toast on successful purge with N deleted ids. */
  purgeOkToast: (n: number) => string;
  /** Toast prefix for purge failures. */
  purgeErrorPrefix: string;
};

export type ArtifactLifecycleConfig<
  TItem extends ArtifactItem,
  TStartInput,
> = {
  /** REST base path with leading slash, no trailing one (e.g. "/models"). */
  apiPath: string;
  /** Cache key for the list query (e.g. "models"). */
  listKey: string;
  /** Cache key prefix for the active query (e.g. "model" → ["model", id]). */
  itemKey: string;
  /** localStorage key for the active artifact id. */
  storageKey: string;
  /** Object key on TItem holding the artifact id. */
  idField: keyof TItem & string;
  /** Build the POST body for a new run from the page's form inputs. */
  buildStartBody: (input: TStartInput) => Record<string, unknown>;
  /** Spanish-aware toast strings. */
  labels: ArtifactLifecycleLabels;
};

export type ArtifactLifecycle<TItem extends ArtifactItem, TStartInput> = {
  list: TItem[];
  listQuery: UseQueryResult<TItem[]>;
  completedList: TItem[];

  activeId: string | null;
  setActiveId: (id: string | null) => void;
  resetActive: () => void;

  active: TItem | undefined;
  activeQuery: UseQueryResult<TItem | undefined>;

  isRunning: boolean;
  hasCompleted: boolean;
  hydrated: boolean;

  start: (input: TStartInput) => void;
  isStarting: boolean;
  cancel: (id: string) => void;
  isCancelling: boolean;
  remove: (id: string) => void;
  isDeleting: boolean;
  cleanup: () => void;
  isCleaning: boolean;
  purge: () => void;
  isPurging: boolean;
  rename: (id: string, name: string) => Promise<void>;
};

export function useArtifactLifecycle<
  TItem extends ArtifactItem,
  TStartInput,
>(config: ArtifactLifecycleConfig<TItem, TStartInput>): ArtifactLifecycle<
  TItem,
  TStartInput
> {
  const queryClient = useQueryClient();
  const [activeId, setActiveIdState] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    // Mount-time hydration: SSR and the first client render must agree on
    // `null` so React doesn't bail out of hydration; we replay from
    // localStorage on the client right after.
    const stored = window.localStorage.getItem(config.storageKey);
    if (stored) setActiveIdState(stored); // eslint-disable-line react-hooks/set-state-in-effect
    setHydrated(true);
  }, [config.storageKey]);

  const setActiveId = (id: string | null) => {
    if (id) window.localStorage.setItem(config.storageKey, id);
    else window.localStorage.removeItem(config.storageKey);
    setActiveIdState(id);
  };

  const resetActive = () => setActiveId(null);

  const listQuery = useQuery<TItem[]>({
    queryKey: [config.listKey],
    queryFn: async () => {
      const { data } = await api.get<TItem[]>(`${config.apiPath}/`);
      return data;
    },
  });

  const activeQuery = useQuery<TItem | undefined>({
    queryKey: [config.itemKey, activeId],
    enabled: !!activeId,
    queryFn: async () => {
      const { data } = await api.get<TItem>(`${config.apiPath}/${activeId}`);
      return data;
    },
    refetchInterval: (query) =>
      query.state.data?.status === "in_progress" ? 2000 : false,
  });

  // When the active run finishes (status leaves in_progress) refresh the
  // catalogue so the history table reflects the new state without a manual
  // reload.
  const activeStatus = activeQuery.data?.status;
  useEffect(() => {
    if (activeStatus && activeStatus !== "in_progress") {
      queryClient.invalidateQueries({ queryKey: [config.listKey] });
    }
  }, [activeStatus, queryClient, config.listKey]);

  // `useMemo` over the query data — not over `listQuery.data ?? []`, which
  // returns a fresh empty array each render and would invalidate every memo
  // depending on it.
  const list = useMemo<TItem[]>(() => listQuery.data ?? [], [listQuery.data]);
  const completedList = useMemo(
    () => list.filter((item) => item.status === "completed"),
    [list],
  );

  const startMutation = useMutation({
    mutationFn: async (input: TStartInput) => {
      const body = config.buildStartBody(input);
      const { data } = await api.post<TItem>(`${config.apiPath}/`, body);
      return data;
    },
    onSuccess: (job) => {
      const newId = (job as Record<string, unknown>)[config.idField] as string;
      window.localStorage.setItem(config.storageKey, newId);
      setActiveIdState(newId);
      toast.success(config.labels.startedToast(newId));
      queryClient.invalidateQueries({ queryKey: [config.listKey] });
    },
    onError: (err) => {
      toast.error(`${config.labels.startErrorPrefix}: ${extractDetail(err)}`);
    },
  });

  const cancelMutation = useMutation({
    mutationFn: async (id: string) => {
      const { data } = await api.post(`${config.apiPath}/${id}/cancel`);
      return data;
    },
    onSuccess: (_data, id) => {
      toast.success("Cancelación solicitada");
      if (activeId === id) {
        queryClient.invalidateQueries({ queryKey: [config.itemKey, id] });
      }
      queryClient.invalidateQueries({ queryKey: [config.listKey] });
    },
    onError: (err) => {
      toast.error(`${config.labels.cancelErrorPrefix}: ${extractDetail(err)}`);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`${config.apiPath}/${id}`);
    },
    onSuccess: (_data, id) => {
      toast.success(config.labels.deletedToast(id));
      if (activeId === id) {
        setActiveIdState(null);
        window.localStorage.removeItem(config.storageKey);
      }
      queryClient.invalidateQueries({ queryKey: [config.listKey] });
    },
    onError: (err) => {
      toast.error(`${config.labels.deleteErrorPrefix}: ${extractDetail(err)}`);
    },
  });

  const cleanupMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.delete(`${config.apiPath}/cleanup`);
      return data as { deleted_ids: string[] };
    },
    onSuccess: (result) => {
      const n = result.deleted_ids?.length ?? 0;
      toast.success(n > 0 ? config.labels.cleanupOkToast(n) : config.labels.cleanupNoopToast);
      queryClient.invalidateQueries({ queryKey: [config.listKey] });
    },
    onError: (err) => {
      toast.error(`${config.labels.cleanupErrorPrefix}: ${extractDetail(err)}`);
    },
  });

  const purgeMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.delete(`${config.apiPath}/purge`);
      return data as { deleted_ids: string[] };
    },
    onSuccess: (result) => {
      const n = result.deleted_ids?.length ?? 0;
      toast.success(config.labels.purgeOkToast(n));
      queryClient.invalidateQueries({ queryKey: [config.listKey] });
    },
    onError: (err) => {
      toast.error(`${config.labels.purgeErrorPrefix}: ${extractDetail(err)}`);
    },
  });

  const renameMutation = useMutation({
    mutationFn: async ({ id, name }: { id: string; name: string }) => {
      await api.patch(`${config.apiPath}/${id}/name`, { name });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [config.listKey] });
    },
  });

  const isRunning = activeQuery.data?.status === "in_progress";
  const hasCompleted = useMemo(
    () =>
      list.some((item) => item.status === "completed") ||
      activeQuery.data?.status === "completed",
    [list, activeQuery.data],
  );

  return {
    list,
    listQuery,
    completedList,
    activeId,
    setActiveId,
    resetActive,
    active: activeQuery.data,
    activeQuery,
    isRunning,
    hasCompleted,
    hydrated,
    start: (input) => startMutation.mutate(input),
    isStarting: startMutation.isPending,
    cancel: (id) => cancelMutation.mutate(id),
    isCancelling: cancelMutation.isPending,
    remove: (id) => deleteMutation.mutate(id),
    isDeleting: deleteMutation.isPending,
    cleanup: () => cleanupMutation.mutate(),
    isCleaning: cleanupMutation.isPending,
    purge: () => purgeMutation.mutate(),
    isPurging: purgeMutation.isPending,
    rename: (id, name) => renameMutation.mutateAsync({ id, name }),
  };
}
