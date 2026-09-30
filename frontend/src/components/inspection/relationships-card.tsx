"use client";

import { useMemo, useState } from "react";
import { Trash2 } from "lucide-react";
import { RelationshipsGraph } from "@/components/inspection/relationships-graph";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { CollapseToggle } from "@/components/ui/collapse-toggle";
import { AdvancedBadge, ADVANCED_CARD_CLASS } from "@/components/ui/advanced-section";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { Autodetect, ForeignKey } from "@/lib/api";
import { NativeSelect } from "@/components/ui/native-select";
import { type AutodetectQuery } from "./utils";

// Editor for the autodetect schema's relational structure (PKs + FKs). Edits
// land in a `draft` lifted to the page so this card and TypesCard share the
// same source of truth; saving PUTs `/autodetect/relationships` and the page
// owns the mutation.
export function RelationshipsCard({
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
      direct: false,
    });
    setDraft(next);
  };

  // The autodetected diagram is always visible — it's central to validating the
  // inspection. The PK/FK editor below it is collapsed by default: most users
  // only glance at the relationships and never need to edit them, so showing
  // all the edit controls up-front is just clutter.
  const [editorOpen, setEditorOpen] = useState(false);

  return (
    <Card>
      <CardHeader className="space-y-0">
        <CardTitle className="text-base">Relaciones Detectadas</CardTitle>
        <CardDescription>
          Diagrama de claves primarias y relaciones entre tablas detectadas.
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

            <div className={cn("rounded-md border", ADVANCED_CARD_CLASS)}>
              <div className="flex items-center justify-between gap-2 px-3 py-2">
                <div>
                  <h3 className="flex items-center gap-2 text-sm font-medium">
                    Editar claves primarias y relaciones
                    <AdvancedBadge tooltip="Avanzado y opcional: edita las claves primarias y las relaciones entre tablas detectadas." />
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    Los cambios solo se aplican al guardar.
                    {dirtyVsSaved && (
                      <span className="ml-1 font-medium text-foreground">
                        Hay cambios sin guardar.
                      </span>
                    )}
                  </p>
                </div>
                <CollapseToggle
                  open={editorOpen}
                  onToggle={() => setEditorOpen((v) => !v)}
                  ariaLabel={editorOpen ? "Contraer editor" : "Expandir editor"}
                />
              </div>
              {editorOpen && (
                <div className="space-y-6 border-t px-3 py-4">
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
                                <NativeSelect
                                  className="h-7 w-auto rounded-md px-2 font-mono text-xs"
                                  value={draft.relationships.pks[table] ?? ""}
                                  onValueChange={(v) => updatePk(table, v)}
                                >
                                  <option value="">— sin PK —</option>
                                  {columnsByTable(table).map((c) => (
                                    <option key={c} value={c}>
                                      {c}
                                    </option>
                                  ))}
                                </NativeSelect>
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
                                <NativeSelect
                                  className="h-7 w-auto rounded-md px-2 font-mono text-xs"
                                  value={fk.parent}
                                  onValueChange={(v) =>
                                    updateFk(i, { parent: v })
                                  }
                                >
                                  {tables.map((t) => (
                                    <option key={t} value={t}>
                                      {t}
                                    </option>
                                  ))}
                                </NativeSelect>
                              </TableCell>
                              <TableCell>
                                <NativeSelect
                                  className="h-7 w-auto rounded-md px-2 font-mono text-xs"
                                  value={fk.child}
                                  onValueChange={(v) =>
                                    updateFk(i, { child: v })
                                  }
                                >
                                  {tables.map((t) => (
                                    <option key={t} value={t}>
                                      {t}
                                    </option>
                                  ))}
                                </NativeSelect>
                              </TableCell>
                              <TableCell>
                                <NativeSelect
                                  className="h-7 w-auto rounded-md px-2 font-mono text-xs"
                                  value={fk.pk_column}
                                  onValueChange={(v) =>
                                    updateFk(i, { pk_column: v })
                                  }
                                >
                                  {columnsByTable(fk.parent).map((c) => (
                                    <option key={c} value={c}>
                                      {c}
                                    </option>
                                  ))}
                                </NativeSelect>
                              </TableCell>
                              <TableCell>
                                <NativeSelect
                                  className="h-7 w-auto rounded-md px-2 font-mono text-xs"
                                  value={fk.fk_column}
                                  onValueChange={(v) =>
                                    updateFk(i, { fk_column: v })
                                  }
                                >
                                  {columnsByTable(fk.child).map((c) => (
                                    <option key={c} value={c}>
                                      {c}
                                    </option>
                                  ))}
                                </NativeSelect>
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

                  {/*
              Save bar lives at the bottom of the editor: as the user scrolls
              down through PKs and FKs adjusting them, the action buttons sit
              naturally where the editing flow ends — instead of at the top
              where they would be out of sight by the time edits are done.
            */}
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
                </div>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
