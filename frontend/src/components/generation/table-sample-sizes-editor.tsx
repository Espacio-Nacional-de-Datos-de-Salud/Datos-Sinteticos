// Per-table sample-size picker for the simulation step.
//
// Mostly AI only honors `sample_size` on **subject** tables (those without a
// context foreign key). For context children it always cascades the row count
// from the parent's generated rows — there is no SDK knob to ask for "exactly N
// rows of this child". We expose only the controls the engine can actually
// satisfy: subject tables are editable, context children are shown read-only at
// their training-time size so the user understands they cascade.
//
// - "original":     send nothing; engine uses each subject's training count.
// - "proportional": scale all subjects by master * (1 / origMasterSize); the
//                   master selector is restricted to subject tables.
// - "advanced":     edit each subject individually; children stay disabled.

import { useState, useEffect } from "react";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";

interface TableSampleSizesEditorProps {
  originalSizes: Record<string, number>;
  subjectTables: string[];
  value: Record<string, number> | null;
  onChange: (sizes: Record<string, number> | null) => void;
}

type Mode = "original" | "proportional" | "advanced";

export function TableSampleSizesEditor({
  originalSizes,
  subjectTables,
  value,
  onChange,
}: TableSampleSizesEditorProps) {
  const [mode, setMode] = useState<Mode>("original");
  const tableNames = Object.keys(originalSizes);
  const subjectSet = new Set(subjectTables);
  // Fall back to first table when subject_tables is empty (e.g. older model
  // without the field) so the UI still functions, just without grey-outs.
  const editableTables = subjectTables.length > 0
    ? tableNames.filter((t) => subjectSet.has(t))
    : tableNames;
  const defaultMaster = editableTables[0] || "";
  const [masterTable, setMasterTable] = useState<string>(defaultMaster);
  const [masterSize, setMasterSize] = useState<string>("");

  // Sync mode with value
  useEffect(() => {
    if (!value) {
      setMode("original");
    }
  }, [value]);

  // When mode changes, if original, clear value
  useEffect(() => {
    if (mode === "original") {
      onChange(null);
    } else if (mode === "proportional" && masterTable) {
      handleProportionalChange(masterSize, masterTable);
    } else if (mode === "advanced" && !value) {
      // Seed only with editable (subject) sizes; children cascade from these.
      const seed: Record<string, number> = {};
      for (const t of editableTables) seed[t] = originalSizes[t];
      onChange(seed);
    }
  }, [mode]);

  const handleProportionalChange = (newMasterSizeStr: string, currentMaster: string) => {
    setMasterSize(newMasterSizeStr);
    const n = parseInt(newMasterSizeStr, 10);
    if (!Number.isFinite(n) || n <= 0) {
      onChange(null);
      return;
    }
    const origMasterSize = originalSizes[currentMaster];
    if (!origMasterSize) return;

    const factor = n / origMasterSize;
    const newSizes: Record<string, number> = {};
    // Only emit sizes for subject tables — sending child sizes is ignored
    // server-side, no point cluttering the request body or the user's preview.
    for (const table of editableTables) {
      newSizes[table] = Math.round(originalSizes[table] * factor);
    }
    onChange(newSizes);
  };

  const handleAdvancedChange = (table: string, sizeStr: string) => {
    const current = value ?? Object.fromEntries(editableTables.map((t) => [t, originalSizes[t]]));
    const n = parseInt(sizeStr, 10);
    onChange({
      ...current,
      [table]: Number.isFinite(n) && n > 0 ? n : originalSizes[table],
    });
  };

  if (tableNames.length === 0) return null;

  const hasChildren = subjectTables.length > 0 && editableTables.length < tableNames.length;

  return (
    <div className="space-y-4 rounded-md border p-4">
      <div className="space-y-2">
        <Label>Cantidad de filas a simular</Label>
        <div className="flex flex-col space-y-2 mt-2">
          <label className="flex items-center space-x-2 font-normal cursor-pointer">
            <input
              type="radio"
              name="mode"
              value="original"
              checked={mode === "original"}
              onChange={(e) => setMode(e.target.value as Mode)}
            />
            <span>Usar misma cantidad que los datos originales</span>
          </label>
          <label className="flex items-center space-x-2 font-normal cursor-pointer">
            <input
              type="radio"
              name="mode"
              value="proportional"
              checked={mode === "proportional"}
              onChange={(e) => setMode(e.target.value as Mode)}
            />
            <span>Ajuste proporcional (modificar tabla maestra)</span>
          </label>
          <label className="flex items-center space-x-2 font-normal cursor-pointer">
            <input
              type="radio"
              name="mode"
              value="advanced"
              checked={mode === "advanced"}
              onChange={(e) => setMode(e.target.value as Mode)}
            />
            <span>Ajustes avanzados (por tabla)</span>
          </label>
        </div>
        {hasChildren && (
          <p className="text-xs text-muted-foreground mt-2">
            Las tablas hijas (con FK de contexto a otra tabla) cascadean su cantidad
            desde la tabla padre y no admiten un tamaño explícito en Mostly AI.
            Solo las tablas <span className="font-mono">subject</span> son editables.
          </p>
        )}
      </div>

      {mode === "proportional" && (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          <div className="space-y-1">
            <Label>Tabla Maestra</Label>
            <select
              value={masterTable}
              onChange={(e) => {
                setMasterTable(e.target.value);
                setMasterSize(originalSizes[e.target.value]?.toString() || "");
              }}
              className="w-full rounded-md border bg-background px-3 py-2 font-mono text-xs"
            >
              {editableTables.map((t) => (
                <option key={t} value={t}>
                  {t} (orig: {originalSizes[t]})
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label>Filas ({masterTable})</Label>
            <Input
              type="number"
              min={1}
              value={masterSize}
              onChange={(e) => handleProportionalChange(e.target.value, masterTable)}
              placeholder={`Ej: ${originalSizes[masterTable]}`}
            />
          </div>
          <div className="space-y-1 col-span-full">
            <Label className="text-muted-foreground">Previsualización (solo tablas subject):</Label>
            <div className="text-xs font-mono text-muted-foreground flex flex-wrap gap-4 mt-1">
              {editableTables.map((t) => (
                <span key={t}>
                  {t}: {value?.[t] ?? originalSizes[t]}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {mode === "advanced" && (
        <div className="grid gap-3 md:grid-cols-3 lg:grid-cols-4">
          {tableNames.map((t) => {
            const editable = subjectTables.length === 0 || subjectSet.has(t);
            return (
              <div key={t} className="space-y-1">
                <Label className="font-mono text-xs">
                  {t}
                  {!editable && (
                    <span className="ml-1 text-muted-foreground font-sans">(cascade)</span>
                  )}
                </Label>
                <Input
                  type="number"
                  min={1}
                  value={value?.[t] ?? originalSizes[t]}
                  onChange={(e) => editable && handleAdvancedChange(t, e.target.value)}
                  disabled={!editable}
                  title={
                    editable
                      ? undefined
                      : "Tabla hija: su cantidad cascadea desde la tabla padre"
                  }
                />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
