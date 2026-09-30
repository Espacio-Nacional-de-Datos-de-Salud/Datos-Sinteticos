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
import { extractDeleteConflict, extractDetail } from "@/lib/errors";

export type DeleteMode = "safe" | "force" | "cascade";

// Every list query whose contents a cascade delete can affect. Deleting an
// inspection can remove downstream models/simulations/evaluations, so a
// successful delete invalidates all of them regardless of which page ran it.
const ALL_LIST_KEYS = ["inspections", "models", "simulations", "evaluations"];

export type DeleteConflictState = {
  /** Artifact the user tried to delete. */
  id: string;
  /** API explanation of why the safe delete was refused. */
  message: string;
  /** Count of downstream artifacts blocking the delete. */
  linkedCount: number;
};

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

  start: (input: TStartInput, name?: string) => void;
  isStarting: boolean;
  cancel: (id: string) => void;
  isCancelling: boolean;
  remove: (id: string) => void;
  isDeleting: boolean;
  /** Set when a safe delete was refused for having downstream jobs. */
  deleteConflict: DeleteConflictState | null;
  /** Dismiss the conflict without deleting. */
  dismissDeleteConflict: () => void;
  /** Retry the blocked delete with "force" (orphan) or "cascade" (downstream). */
  resolveDeleteConflict: (mode: "force" | "cascade") => void;
  cleanup: () => void;
  isCleaning: boolean;
  /** Purge every session of this step. With `cascade` also purge downstream. */
  purge: (cascade?: boolean) => void;
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
  // Each page visit is a clean slate: we deliberately do NOT hydrate the active
  // run from localStorage, so entering a step never pre-selects a past run from
  // its history — the user can't confuse "what was already done" with "what I'm
  // about to launch". We still WRITE localStorage on start/select (below) so
  // downstream steps can read this step's output as their upstream input. With
  // no hydration there's nothing to wait for, so `hydrated` is true from the
  // start (kept on the API for callers that gate on it).
  const [hydrated] = useState(true);
  const [deleteConflict, setDeleteConflict] =
    useState<DeleteConflictState | null>(null);

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
    mutationFn: async ({ input, name }: { input: TStartInput; name?: string }) => {
      const body = config.buildStartBody(input);
      // Include the functional name in the POST body so the backend writes it
      // to the card synchronously before the background task starts, avoiding
      // the race between the PATCH and the background flow overwriting the card.
      const trimmedName = name?.trim();
      const { data } = await api.post<TItem>(`${config.apiPath}/`, {
        ...body,
        ...(trimmedName ? { name: trimmedName } : {}),
      });
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
    mutationFn: async ({ id, mode }: { id: string; mode: DeleteMode }) => {
      await api.delete(`${config.apiPath}/${id}`, {
        params: mode === "safe" ? undefined : { mode },
      });
    },
    onSuccess: (_data, { id }) => {
      toast.success(config.labels.deletedToast(id));
      setDeleteConflict(null);
      if (activeId === id) {
        setActiveIdState(null);
        window.localStorage.removeItem(config.storageKey);
      }
      // A cascade can delete artifacts on other pages, so refresh every list.
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
    mutationFn: async (cascade: boolean) => {
      const { data } = await api.delete(`${config.apiPath}/purge`, {
        params: cascade ? { cascade: true } : undefined,
      });
      return data as { deleted_ids: string[] };
    },
    onSuccess: (result) => {
      const n = result.deleted_ids?.length ?? 0;
      toast.success(config.labels.purgeOkToast(n));
      // A cascade purge can wipe artifacts on other pages, so refresh them all.
      for (const key of ALL_LIST_KEYS) {
        queryClient.invalidateQueries({ queryKey: [key] });
      }
    },
    onError: (err) => {
      toast.error(`${config.labels.purgeErrorPrefix}: ${extractDetail(err)}`);
    },
  });

  const renameMutation = useMutation({
    mutationFn: async ({ id, name }: { id: string; name: string }) => {
      await api.patch(`${config.apiPath}/${id}/name`, { name });
    },
    onSuccess: (_data, { id }) => {
      queryClient.invalidateQueries({ queryKey: [config.listKey] });
      queryClient.invalidateQueries({ queryKey: [config.itemKey, id] });
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
    start: (input, name) => startMutation.mutate({ input, name }),
    isStarting: startMutation.isPending,
    cancel: (id) => cancelMutation.mutate(id),
    isCancelling: cancelMutation.isPending,
    remove: (id) => deleteMutation.mutate({ id, mode: "safe" }),
    isDeleting: deleteMutation.isPending,
    deleteConflict,
    dismissDeleteConflict: () => setDeleteConflict(null),
    resolveDeleteConflict: (mode) => {
      if (deleteConflict) deleteMutation.mutate({ id: deleteConflict.id, mode });
    },
    cleanup: () => cleanupMutation.mutate(),
    isCleaning: cleanupMutation.isPending,
    purge: (cascade = false) => purgeMutation.mutate(cascade),
    isPurging: purgeMutation.isPending,
    rename: (id, name) => renameMutation.mutateAsync({ id, name }),
  };
}
