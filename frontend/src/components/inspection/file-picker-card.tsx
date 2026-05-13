"use client";

import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import axios from "axios";
import { Database, Trash2, Upload } from "lucide-react";

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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, getUploadStats, type DataFile } from "@/lib/api";

import { UploadStorageBar } from "./upload-storage-bar";
import { formatSize } from "./utils";

const EXT_FILTERS = ["csv", "parquet", "json"] as const;
type ExtFilter = (typeof EXT_FILTERS)[number] | "all";

// File-selection card shown at the top of the Inspección page. Owns the
// pure UI bits (ext filter, source filter, profiling toggle) and the
// upload/delete mutations whose results aren't read elsewhere on the page.
// Selection is lifted to the parent because the SelectionPreviewCard reads
// it too.
export function FilePickerCard({
  selected,
  onToggleSelected,
  onSelectionChange,
  onClearUploadsFromSelection,
  allowServerFiles,
  isStartDisabled,
  isStarting,
  onStart,
}: {
  selected: Set<string>;
  onToggleSelected: (path: string) => void;
  onSelectionChange: (next: Set<string>) => void;
  /** Called after delete-uploads succeeds so the parent can prune its set. */
  onClearUploadsFromSelection: () => void;
  allowServerFiles: boolean;
  isStartDisabled: boolean;
  isStarting: boolean;
  onStart: (enableProfiling: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [extFilter, setExtFilter] = useState<ExtFilter>("all");
  const [enableProfiling, setEnableProfiling] = useState<boolean>(true);
  const [sourceFilter, setSourceFilter] = useState<"uploads" | "server">(
    "uploads",
  );
  const fileInputRef = useRef<HTMLInputElement | null>(null);

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
      onClearUploadsFromSelection();
      queryClient.invalidateQueries({ queryKey: ["files"] });
      queryClient.invalidateQueries({ queryKey: ["upload-stats"] });
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Error desconocido";
      toast.error(`No se pudieron borrar los uploads: ${msg}`);
    },
  });

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

  const visiblePaths = files.map((f) => f.path);
  const allVisibleSelected =
    visiblePaths.length > 0 && visiblePaths.every((p) => selected.has(p));

  const toggleAllVisible = () => {
    const next = new Set(selected);
    if (allVisibleSelected) {
      for (const p of visiblePaths) next.delete(p);
    } else {
      for (const p of visiblePaths) next.add(p);
    }
    onSelectionChange(next);
  };

  return (
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

            {/*
              Bulk select / clear: with the current ext + source filters
              applied, "Seleccionar todos" picks every visible file in
              one click — much faster than ticking them one by one when
              the user wants the whole batch.
            */}
            {files.length > 0 && (
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <button
                  type="button"
                  onClick={toggleAllVisible}
                  className="rounded-md border border-muted bg-background px-2 py-1 text-muted-foreground hover:bg-accent"
                >
                  {allVisibleSelected
                    ? `Quitar selección (${visiblePaths.length})`
                    : `Seleccionar todos (${visiblePaths.length})`}
                </button>
                {selected.size > 0 && (
                  <span className="text-muted-foreground">
                    {selected.size} seleccionado(s)
                  </span>
                )}
              </div>
            )}

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
                        onClick={() => onToggleSelected(f.path)}
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
              disabled={isStartDisabled || isStarting}
              onClick={() => onStart(enableProfiling)}
            >
              {isStarting
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
  );
}
