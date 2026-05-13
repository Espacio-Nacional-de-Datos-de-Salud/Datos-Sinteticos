// Per-kind input widgets for axis values. Both the grid-combinations dialog
// and the variant dialog feed the same `AxisField` vocabulary, so the value
// editing UI lives here once. Two top-level components are exported:
//
//   • `AxisValuesEditor`       — multi-value editor (grid mode). The user
//     enumerates several values along one axis; dialog renders the cartesian
//     product across axes.
//   • `AxisSingleValueEditor`  — single-value editor (variant mode). Each
//     variant patches a field with exactly one value, no enumeration.
//
// Implementation note: the per-kind inputs are intentionally small / native.
// We don't pull in a combobox library — the existing pipelines page uses
// raw `<select>` elements styled via the shared `SELECT_CLASS`, and this
// matches that look.

"use client";

import { useState } from "react";
import { Plus, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type {
  ConfigFile,
  DataFile,
  InspectionSummary,
  ModelSummary,
  SimulationSummary,
} from "@/lib/api";
import { SELECT_CLASS } from "@/lib/ui";
import { cn } from "@/lib/utils";

import {
  AXIS_FIELD_KIND,
  type AxisField,
  type AxisFieldKind,
  type AxisValue,
} from "./expansion";
import { MOSTLY_AI_MODELS } from "./types";

// Catalogues injected from the page so editors can render dropdowns over
// real data without each refetching independently.
export type AxisCatalogues = {
  files: DataFile[];
  models: ModelSummary[];
  rulesConfigs: ConfigFile[];
  inspections: InspectionSummary[];
  simulations: SimulationSummary[];
};

// ---------------------------------------------------------------------------
// Multi-value editor (grid mode)
// ---------------------------------------------------------------------------

export function AxisValuesEditor({
  field,
  values,
  onChange,
  catalogues,
}: {
  field: AxisField;
  values: AxisValue[];
  onChange: (next: AxisValue[]) => void;
  catalogues: AxisCatalogues;
}) {
  const kind = AXIS_FIELD_KIND[field];

  if (kind === "numeric" || kind === "text") {
    return (
      <FreeFormChipsEditor
        values={values}
        onChange={onChange}
        kind={kind}
        placeholder={
          kind === "numeric"
            ? "ej: 10, 20, 30"
            : "ej: ',', ';', '|'"
        }
      />
    );
  }

  if (kind === "tri") {
    return <TriEditor values={values} onChange={onChange} />;
  }

  if (kind === "model") {
    return (
      <EnumMultiEditor
        values={values}
        onChange={onChange}
        options={MOSTLY_AI_MODELS.map((m) => ({ label: m, raw: m }))}
        placeholder="Añade un modelo…"
      />
    );
  }

  if (kind === "rules") {
    return (
      <EnumMultiEditor
        values={values}
        onChange={onChange}
        options={catalogues.rulesConfigs.map((r) => ({
          label: r.id,
          raw: `config/${r.id}`,
        }))}
        placeholder="Añade un rules.yaml…"
      />
    );
  }

  if (kind === "modelId") {
    return (
      <EnumMultiEditor
        values={values}
        onChange={onChange}
        options={catalogues.models
          .filter((m) => m.status === "completed")
          .map((m) => ({
            label: m.model_name || m.model_id,
            raw: m.model_id,
          }))}
        placeholder="Añade un modelo entrenado…"
      />
    );
  }

  if (kind === "inspectionId") {
    return (
      <EnumMultiEditor
        values={values}
        onChange={onChange}
        options={catalogues.inspections
          .filter((i) => i.status === "completed")
          .map((i) => ({
            label: i.inspection_name || i.inspection_id,
            raw: i.inspection_id,
          }))}
        placeholder="Añade una inspección…"
      />
    );
  }

  if (kind === "simulationId") {
    return (
      <EnumMultiEditor
        values={values}
        onChange={onChange}
        options={catalogues.simulations
          .filter((s) => s.status === "completed")
          .map((s) => ({
            label: s.simulation_name || s.simulation_id,
            raw: s.simulation_id,
          }))}
        placeholder="Añade una simulación…"
      />
    );
  }

  // filesGroup: each value carries a list of files (raw: string[]).
  return (
    <FilesGroupEditor
      values={values}
      onChange={onChange}
      files={catalogues.files}
    />
  );
}

// ---------------------------------------------------------------------------
// Single-value editor (variant mode)
// ---------------------------------------------------------------------------

export function AxisSingleValueEditor({
  field,
  value,
  onChange,
  catalogues,
}: {
  field: AxisField;
  value: AxisValue | null;
  onChange: (next: AxisValue | null) => void;
  catalogues: AxisCatalogues;
}) {
  const kind = AXIS_FIELD_KIND[field];

  if (kind === "numeric") {
    return (
      <Input
        type="number"
        value={typeof value?.raw === "string" ? value.raw : ""}
        placeholder="—"
        onChange={(e) => {
          const v = e.target.value;
          onChange(v ? { label: v, raw: v } : null);
        }}
      />
    );
  }

  if (kind === "text") {
    return (
      <Input
        value={typeof value?.raw === "string" ? value.raw : ""}
        placeholder="—"
        onChange={(e) => {
          const v = e.target.value;
          onChange(v ? { label: v, raw: v } : null);
        }}
      />
    );
  }

  if (kind === "tri") {
    return (
      <select
        className={SELECT_CLASS}
        value={typeof value?.raw === "string" ? value.raw : ""}
        onChange={(e) => {
          const v = e.target.value;
          if (v === "true" || v === "false") {
            onChange({ label: v === "true" ? "on" : "off", raw: v });
          } else {
            onChange(null);
          }
        }}
      >
        <option value="">—</option>
        <option value="true">Activado</option>
        <option value="false">Desactivado</option>
      </select>
    );
  }

  if (
    kind === "model"
    || kind === "rules"
    || kind === "modelId"
    || kind === "inspectionId"
    || kind === "simulationId"
  ) {
    const options = enumOptionsFor(kind, catalogues);
    return (
      <select
        className={SELECT_CLASS}
        value={typeof value?.raw === "string" ? value.raw : ""}
        onChange={(e) => {
          const opt = options.find((o) => o.raw === e.target.value);
          onChange(opt ? { label: opt.label, raw: opt.raw } : null);
        }}
      >
        <option value="">—</option>
        {options.map((o) => (
          <option key={o.raw} value={o.raw}>
            {o.label}
          </option>
        ))}
      </select>
    );
  }

  // filesGroup single: one multi-file selection that becomes the variant's
  // train.files. Label defaults to the basename of the first file so the
  // generated job name stays informative.
  return (
    <SingleFilesGroup
      value={value}
      onChange={onChange}
      files={catalogues.files}
    />
  );
}

function enumOptionsFor(
  kind: AxisFieldKind,
  catalogues: AxisCatalogues,
): { label: string; raw: string }[] {
  if (kind === "model") return MOSTLY_AI_MODELS.map((m) => ({ label: m, raw: m }));
  if (kind === "rules")
    return catalogues.rulesConfigs.map((r) => ({
      label: r.id,
      raw: `config/${r.id}`,
    }));
  if (kind === "modelId")
    return catalogues.models
      .filter((m) => m.status === "completed")
      .map((m) => ({ label: m.model_name || m.model_id, raw: m.model_id }));
  if (kind === "inspectionId")
    return catalogues.inspections
      .filter((i) => i.status === "completed")
      .map((i) => ({
        label: i.inspection_name || i.inspection_id,
        raw: i.inspection_id,
      }));
  if (kind === "simulationId")
    return catalogues.simulations
      .filter((s) => s.status === "completed")
      .map((s) => ({
        label: s.simulation_name || s.simulation_id,
        raw: s.simulation_id,
      }));
  return [];
}

// ---------------------------------------------------------------------------
// Sub-editors
// ---------------------------------------------------------------------------

// One text input that splits on commas → chips. Rebuilds the input string from
// the value list so the user can see what they've added even after the chips
// rendered. Numeric kind enforces digits-only at parse time.
function FreeFormChipsEditor({
  values,
  onChange,
  kind,
  placeholder,
}: {
  values: AxisValue[];
  onChange: (next: AxisValue[]) => void;
  kind: "numeric" | "text";
  placeholder: string;
}) {
  const [draft, setDraft] = useState("");

  const commit = () => {
    const tokens = draft
      .split(",")
      .map((t) => t.trim())
      .filter((t) => t.length > 0)
      .filter((t) => (kind === "numeric" ? !Number.isNaN(Number(t)) : true));
    if (tokens.length === 0) return;
    const existing = new Set(values.map((v) => v.raw));
    const additions = tokens
      .filter((t) => !existing.has(t))
      .map((t) => ({ label: t, raw: t }));
    if (additions.length > 0) onChange([...values, ...additions]);
    setDraft("");
  };

  return (
    <div className="space-y-2">
      {values.length > 0 && (
        <ChipList
          values={values}
          onRemove={(idx) => onChange(values.filter((_, i) => i !== idx))}
        />
      )}
      <div className="flex gap-2">
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={placeholder}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              commit();
            }
          }}
          className="h-9"
        />
        <Button type="button" size="sm" variant="outline" onClick={commit}>
          <Plus className="mr-1 h-3 w-3" /> Añadir
        </Button>
      </div>
      <p className="text-[11px] text-muted-foreground">
        Separa con comas o pulsa Enter para añadir.
      </p>
    </div>
  );
}

function TriEditor({
  values,
  onChange,
}: {
  values: AxisValue[];
  onChange: (next: AxisValue[]) => void;
}) {
  const has = (raw: string) => values.some((v) => v.raw === raw);
  const toggle = (raw: "true" | "false", label: string) => {
    if (has(raw)) onChange(values.filter((v) => v.raw !== raw));
    else onChange([...values, { label, raw }]);
  };
  return (
    <div className="flex gap-2">
      <ToggleChip checked={has("true")} onClick={() => toggle("true", "on")}>
        Activado
      </ToggleChip>
      <ToggleChip checked={has("false")} onClick={() => toggle("false", "off")}>
        Desactivado
      </ToggleChip>
    </div>
  );
}

function ToggleChip({
  checked,
  onClick,
  children,
}: {
  checked: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-md border px-3 py-1.5 text-xs font-semibold transition-colors",
        checked
          ? "border-[#00215C] bg-[#00215C] text-white"
          : "border-border bg-background text-muted-foreground hover:bg-accent/40",
      )}
    >
      {children}
    </button>
  );
}

function EnumMultiEditor({
  values,
  onChange,
  options,
  placeholder,
}: {
  values: AxisValue[];
  onChange: (next: AxisValue[]) => void;
  options: { label: string; raw: string }[];
  placeholder: string;
}) {
  const remaining = options.filter((o) => !values.some((v) => v.raw === o.raw));
  return (
    <div className="space-y-2">
      {values.length > 0 && (
        <ChipList
          values={values}
          onRemove={(idx) => onChange(values.filter((_, i) => i !== idx))}
        />
      )}
      <select
        className={SELECT_CLASS}
        value=""
        onChange={(e) => {
          const next = options.find((o) => o.raw === e.target.value);
          if (next) onChange([...values, next]);
        }}
      >
        <option value="">{placeholder}</option>
        {remaining.map((o) => (
          <option key={o.raw} value={o.raw}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

// File-group editor: each AxisValue carries a list of file paths. The user
// labels each group (used in the generated job name); empty labels fall back
// to the first filename's basename so we always have something printable.
function FilesGroupEditor({
  values,
  onChange,
  files,
}: {
  values: AxisValue[];
  onChange: (next: AxisValue[]) => void;
  files: DataFile[];
}) {
  const updateGroup = (idx: number, patch: Partial<AxisValue>) => {
    onChange(values.map((v, i) => (i === idx ? { ...v, ...patch } : v)));
  };

  const addGroup = () => {
    onChange([...values, { label: `grupo_${values.length + 1}`, raw: [] }]);
  };

  return (
    <div className="space-y-2">
      {values.map((group, idx) => (
        <div
          key={idx}
          className="space-y-2 rounded border border-border bg-muted/20 p-2.5"
        >
          <div className="flex items-center gap-2">
            <Label className="text-[10px] uppercase tracking-wide text-muted-foreground">
              Etiqueta
            </Label>
            <Input
              value={group.label}
              onChange={(e) => updateGroup(idx, { label: e.target.value })}
              className="h-7 flex-1 text-xs"
              placeholder={`grupo_${idx + 1}`}
            />
            <button
              type="button"
              aria-label="Eliminar grupo"
              onClick={() => onChange(values.filter((_, i) => i !== idx))}
              className="text-muted-foreground hover:text-red-600"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          <FilesPickerList
            files={files}
            selected={Array.isArray(group.raw) ? group.raw : []}
            onChange={(next) => updateGroup(idx, { raw: next })}
          />
        </div>
      ))}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={addGroup}
        className="w-full"
      >
        <Plus className="mr-1 h-3 w-3" /> Añadir grupo de archivos
      </Button>
    </div>
  );
}

function SingleFilesGroup({
  value,
  onChange,
  files,
}: {
  value: AxisValue | null;
  onChange: (next: AxisValue | null) => void;
  files: DataFile[];
}) {
  const selected = value && Array.isArray(value.raw) ? value.raw : [];
  return (
    <FilesPickerList
      files={files}
      selected={selected}
      onChange={(next) => {
        if (next.length === 0) {
          onChange(null);
          return;
        }
        // Auto-derive label from the first filename so generated job names
        // get something more informative than "files".
        const first = files.find((f) => f.path === next[0]);
        const label = first?.name?.split(".")[0] ?? "files";
        onChange({ label, raw: next });
      }}
    />
  );
}

function FilesPickerList({
  files,
  selected,
  onChange,
}: {
  files: DataFile[];
  selected: string[];
  onChange: (next: string[]) => void;
}) {
  const remaining = files.filter((f) => !selected.includes(f.path));
  return (
    <div className="space-y-1.5">
      {selected.length > 0 && (
        <ul className="space-y-1">
          {selected.map((path) => (
            <li
              key={path}
              className="flex items-center justify-between gap-2 rounded-md border border-border bg-background px-2.5 py-1.5 text-xs"
            >
              <span className="truncate font-mono">{path}</span>
              <button
                type="button"
                aria-label="Quitar archivo"
                className="text-muted-foreground hover:text-foreground"
                onClick={() => onChange(selected.filter((p) => p !== path))}
              >
                <X className="h-3 w-3" />
              </button>
            </li>
          ))}
        </ul>
      )}
      <select
        className={SELECT_CLASS}
        value=""
        onChange={(e) => {
          const next = e.target.value;
          if (next) onChange([...selected, next]);
        }}
      >
        <option value="">Añade archivos…</option>
        {remaining.map((f) => (
          <option key={f.path} value={f.path}>
            {f.name}
          </option>
        ))}
      </select>
    </div>
  );
}

function ChipList({
  values,
  onRemove,
}: {
  values: AxisValue[];
  onRemove: (idx: number) => void;
}) {
  return (
    <ul className="flex flex-wrap gap-1.5">
      {values.map((v, idx) => (
        <li
          key={idx}
          className="flex items-center gap-1.5 rounded-full border border-border bg-background px-2.5 py-1 text-[11px]"
        >
          <span className="font-mono">{v.label}</span>
          <button
            type="button"
            aria-label="Quitar valor"
            className="text-muted-foreground hover:text-foreground"
            onClick={() => onRemove(idx)}
          >
            <X className="h-3 w-3" />
          </button>
        </li>
      ))}
    </ul>
  );
}
