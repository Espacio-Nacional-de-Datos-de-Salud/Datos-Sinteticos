// Load / save toolbar for the live rules editor on Reglas de negocio.
//
// The live editor is backed by the shared rules.yaml. This bar lets the user:
//   - Load a rule set into the live editor from either the saved library or a
//     past BRC run snapshot, then iterate from there.
//   - Save the current rule set to the library (auto-named, optional functional
//     name) without running anything, for reuse later.
//
// Loading writes the chosen YAML into rules.yaml (PUT /configs/rules) and
// invalidates the queries the editor + banner read, so both refresh in place.

"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { FolderOpen, Save, Trash2 } from "lucide-react";

import { api, type ConfigContent } from "@/lib/api";
import { extractDetail } from "@/lib/errors";
import { getBrcRulesSnapshot, type BRCSummary } from "@/lib/brc";
import {
  deleteRulePreset,
  getRulePresetRules,
  listRulePresets,
  renameRulePreset,
  saveRulePreset,
} from "@/lib/rule-presets";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/native-select";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EditableName } from "@/components/jobs/editable-name";
import { NamePromptDialog } from "@/components/ui/name-prompt-dialog";

// Encode the load source + id into the <select> value so a single control can
// offer both sources. Decoded in handleLoad.
const PRESET_PREFIX = "preset:";
const BRC_PREFIX = "brc:";

// Total number of columns marked for deletion across all tables.
function countExcluded(excluded: Record<string, string[]> | undefined): number {
  return Object.values(excluded ?? {}).reduce((n, cols) => n + cols.length, 0);
}

// "6 reglas · 3 col. a eliminar" — the col. part is omitted when there are none.
function countsLabel(
  rulesCount: number,
  excluded: Record<string, string[]> | undefined,
): string {
  const parts = [`${rulesCount} ${rulesCount === 1 ? "regla" : "reglas"}`];
  const excl = countExcluded(excluded);
  if (excl > 0) parts.push(`${excl} col. a eliminar`);
  return parts.join(" · ");
}

export function RulesLibraryBar({
  inspectionId,
  currentExcludedColumns,
  completedBrcs,
}: {
  inspectionId: string | null;
  // The selected upload's current Reglas-de-negocio column deletions
  // (autodetect.rules_excluded_columns) — saved with the rule set.
  currentExcludedColumns: Record<string, string[]>;
  completedBrcs: BRCSummary[];
}) {
  const queryClient = useQueryClient();
  const [saveDialog, setSaveDialog] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const presetsQuery = useQuery({
    queryKey: ["rule-presets"],
    queryFn: listRulePresets,
  });
  const presets = useMemo(() => presetsQuery.data ?? [], [presetsQuery.data]);
  const hasLoadable = presets.length > 0 || completedBrcs.length > 0;

  // After any change to rules.yaml, refresh the editor, the live banner and the
  // compliance evaluation — same keys those components read. Column deletions
  // live on the inspection autodetect, so refresh that too.
  const refreshLiveRules = () => {
    queryClient.invalidateQueries({ queryKey: ["config", "rules"] });
    queryClient.invalidateQueries({ queryKey: ["rules-banner"] });
    queryClient.invalidateQueries({ queryKey: ["rules-compliance"] });
    if (inspectionId) {
      queryClient.invalidateQueries({ queryKey: ["autodetect", inspectionId] });
    }
  };

  // Apply a rule set's column deletions to the selected upload. Skipped when no
  // upload is selected (rules still load; deletions can't be targeted).
  const applyExcludedColumns = async (excluded: Record<string, string[]>) => {
    if (!inspectionId) return;
    await api.put(`/inspections/${inspectionId}/autodetect/rules-exclusions`, {
      excluded_columns: excluded ?? {},
    });
  };

  const loadMutation = useMutation({
    mutationFn: async (value: string) => {
      let content: string;
      let excluded: Record<string, string[]> = {};
      if (value.startsWith(PRESET_PREFIX)) {
        const presetId = value.slice(PRESET_PREFIX.length);
        content = await getRulePresetRules(presetId);
        excluded =
          presets.find((p) => p.preset_id === presetId)?.excluded_columns ?? {};
      } else if (value.startsWith(BRC_PREFIX)) {
        const brcId = value.slice(BRC_PREFIX.length);
        content = await getBrcRulesSnapshot(brcId);
        const brc = completedBrcs.find((b) => b.brc_id === brcId);
        // Runs created before rules_excluded_columns was snapshotted fall back
        // to the card's excluded_columns union (best-effort for old history).
        excluded = brc?.rules_excluded_columns ?? brc?.excluded_columns ?? {};
      } else {
        throw new Error("Origen de reglas desconocido.");
      }
      await api.put<ConfigContent>("/configs/rules", { content });
      await applyExcludedColumns(excluded);
    },
    onSuccess: () => {
      toast.success("Reglas cargadas en el editor.");
      refreshLiveRules();
    },
    onError: (err) =>
      toast.error(`No se pudieron cargar las reglas: ${extractDetail(err)}`),
  });

  const saveMutation = useMutation({
    mutationFn: async (name: string) => {
      const { data } = await api.get<ConfigContent>("/configs/rules");
      return saveRulePreset(data.content, name || undefined, currentExcludedColumns);
    },
    onSuccess: (preset) => {
      toast.success(`Conjunto guardado: ${preset.preset_name}`);
      queryClient.invalidateQueries({ queryKey: ["rule-presets"] });
    },
    onError: (err) =>
      toast.error(`No se pudo guardar el conjunto: ${extractDetail(err)}`),
  });

  const renameMutation = useMutation({
    mutationFn: ({ presetId, name }: { presetId: string; name: string }) =>
      renameRulePreset(presetId, name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["rule-presets"] });
    },
    onError: (err) => toast.error(`No se pudo renombrar: ${extractDetail(err)}`),
  });

  const deleteMutation = useMutation({
    mutationFn: (presetId: string) => deleteRulePreset(presetId),
    onSuccess: () => {
      toast.success("Conjunto eliminado.");
      queryClient.invalidateQueries({ queryKey: ["rule-presets"] });
    },
    onError: (err) => toast.error(`No se pudo eliminar: ${extractDetail(err)}`),
  });

  const presetToDelete = presets.find((p) => p.preset_id === confirmDelete);

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Biblioteca de reglas</CardTitle>
        <CardDescription>
          Carga un conjunto de reglas guardado o el de una ejecución anterior
          para iterar sobre él. A la vez, puedes guardar el conjunto actual para
          reutilizarlo más tarde. Un conjunto incluye las reglas lógicas, las
          columnas derivadas y las columnas marcadas para eliminar.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          {/* NativeSelect is a Base-UI wrapper that only collects <option>
              children (no <optgroup> support), so groups are rendered as
              disabled header options acting as separators. */}
          <NativeSelect
            aria-label="Cargar conjunto de reglas"
            value=""
            onValueChange={(v) => {
              if (v) loadMutation.mutate(v);
            }}
            disabled={loadMutation.isPending || !hasLoadable}
            placeholder={
              loadMutation.isPending
                ? "Cargando…"
                : hasLoadable
                  ? "Cargar conjunto de reglas…"
                  : "No hay conjuntos guardados ni ejecuciones"
            }
            className="h-9 w-auto min-w-[28rem] max-w-full rounded-md px-2 text-sm"
          >
            <option value="" disabled>
              {loadMutation.isPending
                ? "Cargando…"
                : "Cargar conjunto de reglas…"}
            </option>
            {presets.length > 0 && (
              <option value="__lib_header" disabled>
                — Biblioteca —
              </option>
            )}
            {presets.map((p) => (
              <option key={p.preset_id} value={`${PRESET_PREFIX}${p.preset_id}`}>
                {p.preset_name} · {countsLabel(p.rules_count, p.excluded_columns)}
              </option>
            ))}
            {completedBrcs.length > 0 && (
              <option value="__brc_header" disabled>
                — Historial de ejecuciones —
              </option>
            )}
            {completedBrcs.map((b) => (
              <option key={b.brc_id} value={`${BRC_PREFIX}${b.brc_id}`}>
                {b.brc_id}
                {b.brc_name && b.brc_name !== b.brc_id ? ` · ${b.brc_name}` : ""}
                {" · "}
                {countsLabel(
                  b.rules_count,
                  b.rules_excluded_columns ?? b.excluded_columns,
                )}
              </option>
            ))}
          </NativeSelect>

          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setSaveDialog(true)}
            disabled={saveMutation.isPending}
          >
            <Save className="mr-1.5 h-3.5 w-3.5" />
            {saveMutation.isPending ? "Guardando…" : "Guardar conjunto actual"}
          </Button>
        </div>

        {presets.length > 0 && (
          <div className="space-y-1.5">
            <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <FolderOpen className="h-3.5 w-3.5" />
              Conjuntos guardados
            </p>
            <ul className="divide-y rounded-md border">
              {presets.map((p) => (
                <li
                  key={p.preset_id}
                  className="flex items-center justify-between gap-2 px-3 py-1.5"
                >
                  <div className="min-w-0 flex-1">
                    <EditableName
                      name={p.preset_name}
                      existingNames={presets.map((x) => x.preset_name)}
                      onSave={async (name) => {
                        await renameMutation.mutateAsync({
                          presetId: p.preset_id,
                          name,
                        });
                      }}
                    />
                  </div>
                  <span className="shrink-0 text-[11px] text-muted-foreground">
                    {p.rules_count} {p.rules_count === 1 ? "regla" : "reglas"}
                    {countExcluded(p.excluded_columns) > 0 &&
                      ` · ${countExcluded(p.excluded_columns)} col. a eliminar`}
                  </span>
                  <button
                    type="button"
                    onClick={() => setConfirmDelete(p.preset_id)}
                    className="shrink-0 rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                    aria-label="Eliminar conjunto"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>

      <NamePromptDialog
        open={saveDialog}
        title="Guardar conjunto de reglas"
        description="Asigna un nombre funcional para reconocerlo más tarde. Puedes dejarlo en blanco y se generará uno automáticamente."
        confirmLabel="Guardar"
        onConfirm={(name) => {
          saveMutation.mutate(name);
          setSaveDialog(false);
        }}
        onCancel={() => setSaveDialog(false)}
      />

      <ConfirmDialog
        open={confirmDelete !== null}
        title="¿Eliminar conjunto de reglas?"
        description={`Se eliminará "${presetToDelete?.preset_name ?? ""}" de la biblioteca. Esta acción no afecta a las reglas cargadas en el editor.`}
        confirmLabel="Eliminar"
        onConfirm={() => {
          if (confirmDelete) deleteMutation.mutate(confirmDelete);
          setConfirmDelete(null);
        }}
        onCancel={() => setConfirmDelete(null)}
      />
    </Card>
  );
}