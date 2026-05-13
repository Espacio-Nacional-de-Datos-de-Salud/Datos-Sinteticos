// Per-job "Expandir en variantes" dialog. Takes a single base job and lets the
// user define a hand-picked list of variants (each variant is a sparse patch
// over the base — typically just one or two fields tweaked). Each variant
// produces one new job; this is the right tool when sweeps are sparse rather
// than full cartesian product.
//
// Typical use case: "I have a simulate-only job that resumes from model X.
// Run it with sample sizes 1k / 5k / 10k, plus one variant with DP enabled."

"use client";

import { useMemo, useState } from "react";
import { Copy, Plus, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import {
  AxisSingleValueEditor,
  type AxisCatalogues,
} from "./axis-value-editor";
import {
  AXIS_LABELS,
  type AxisField,
  type AxisValue,
  type Variant,
  expandVariants,
  isAxisApplicable,
} from "./expansion";
import type { Job } from "./types";
import type { ApplyMode } from "./combinations-dialog";
import { SELECT_CLASS } from "@/lib/ui";

type VariantDraft = {
  label: string;
  patches: { field: AxisField; value: AxisValue | null }[];
};

export function VariantsDialog({
  open,
  baseJob,
  baseIndex,
  catalogues,
  onClose,
  onApply,
}: {
  open: boolean;
  baseJob: Job | null;
  baseIndex: number;
  catalogues: AxisCatalogues;
  onClose: () => void;
  onApply: (input: {
    baseIndex: number;
    generated: Job[];
    mode: ApplyMode;
  }) => void;
}) {
  const [variants, setVariants] = useState<VariantDraft[]>([
    { label: "v1", patches: [] },
  ]);
  const [mode, setMode] = useState<ApplyMode>("insertAfter");

  const applicableFields = useMemo(
    () =>
      baseJob
        ? (Object.keys(AXIS_LABELS) as AxisField[]).filter((f) =>
            isAxisApplicable(f, baseJob),
          )
        : [],
    [baseJob],
  );

  // Build the structured `Variant[]` once per draft change so `expandVariants`
  // sees a stable reference. Doing it inside `useMemo` also keeps the preview
  // computation in one place.
  const generated = useMemo(() => {
    if (!baseJob) return [];
    const built: Variant[] = variants.map((v) => ({
      label: v.label || "v",
      patch: Object.fromEntries(
        v.patches
          .filter((p) => p.value !== null)
          // `value` is non-null per the filter above; cast covers narrowing.
          .map((p) => [p.field, (p.value as AxisValue).raw]),
      ),
    }));
    return expandVariants(baseJob, built);
  }, [baseJob, variants]);

  // Hooks above; conditional render below to keep rules-of-hooks happy.
  if (!open || !baseJob) return null;

  const updateVariant = (idx: number, patch: Partial<VariantDraft>) => {
    setVariants((cur) => cur.map((v, i) => (i === idx ? { ...v, ...patch } : v)));
  };
  const removeVariant = (idx: number) => {
    setVariants((cur) => cur.filter((_, i) => i !== idx));
  };
  const addVariant = () => {
    setVariants((cur) => [
      ...cur,
      { label: `v${cur.length + 1}`, patches: [] },
    ]);
  };

  const apply = () => {
    if (generated.length === 0) return;
    onApply({ baseIndex, generated, mode });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-full max-w-3xl flex-col rounded-lg border border-border bg-card shadow-2xl">
        <header className="flex items-center justify-between border-b border-border px-6 py-4">
          <div className="flex items-center gap-3">
            <Copy className="h-5 w-5 text-[#00215C]" />
            <div>
              <div className="text-[10px] font-bold uppercase tracking-[0.08em] text-muted-foreground">
                Expandir job en variantes
              </div>
              <h3 className="text-lg font-semibold tracking-tight">{baseJob.name}</h3>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <X className="h-5 w-5" />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-6">
          <div className="space-y-4">
            <p className="text-[11px] text-muted-foreground">
              Cada variante clona <code>{baseJob.name}</code> y aplica los
              cambios indicados. Los campos que no toques se heredan tal cual.
            </p>

            <div className="space-y-3">
              {variants.map((variant, idx) => (
                <VariantCard
                  key={idx}
                  variant={variant}
                  applicableFields={applicableFields}
                  catalogues={catalogues}
                  onChange={(patch) => updateVariant(idx, patch)}
                  onRemove={
                    variants.length > 1 ? () => removeVariant(idx) : undefined
                  }
                />
              ))}
            </div>

            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={addVariant}
              className="w-full"
            >
              <Plus className="mr-1 h-3 w-3" /> Añadir variante
            </Button>

            <section className="space-y-2 pt-2">
              <Label className="text-xs">Aplicar como</Label>
              <div className="flex flex-col gap-1.5 text-xs">
                <RadioRow
                  current={mode}
                  value="insertAfter"
                  onChange={setMode}
                  label="Insertar variantes después del job base (mantener base)"
                />
                <RadioRow
                  current={mode}
                  value="replace"
                  onChange={setMode}
                  label="Reemplazar el job base con las variantes"
                />
              </div>
            </section>

            {generated.length > 0 && (
              <section className="rounded-md border border-border bg-muted/20 p-4">
                <div className="text-[10px] font-bold uppercase tracking-[0.08em] text-muted-foreground">
                  Previsualización
                </div>
                <ul className="mt-1 space-y-1">
                  {generated.map((j, i) => (
                    // Index-keyed: dedupe makes names unique post-expansion,
                    // but transient duplicates can still appear mid-edit.
                    <li
                      key={i}
                      className="truncate font-mono text-[11px] text-muted-foreground"
                    >
                      • {j.name}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        </div>

        <footer className="flex justify-end gap-2 border-t border-border bg-muted/20 px-6 py-4">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={apply}
            disabled={generated.length === 0}
          >
            <Copy className="mr-1 h-3.5 w-3.5" /> Generar {generated.length || ""}
          </Button>
        </footer>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------

function VariantCard({
  variant,
  applicableFields,
  catalogues,
  onChange,
  onRemove,
}: {
  variant: VariantDraft;
  applicableFields: AxisField[];
  catalogues: AxisCatalogues;
  onChange: (patch: Partial<VariantDraft>) => void;
  onRemove?: () => void;
}) {
  const updatePatch = (
    idx: number,
    patch: Partial<{ field: AxisField; value: AxisValue | null }>,
  ) => {
    onChange({
      patches: variant.patches.map((p, i) => (i === idx ? { ...p, ...patch } : p)),
    });
  };
  const removePatch = (idx: number) => {
    onChange({ patches: variant.patches.filter((_, i) => i !== idx) });
  };
  const addPatch = () => {
    const used = new Set(variant.patches.map((p) => p.field));
    const next = applicableFields.find((f) => !used.has(f));
    if (!next) return;
    onChange({
      patches: [...variant.patches, { field: next, value: null }],
    });
  };

  return (
    <div className="space-y-2.5 rounded-md border border-border bg-background p-3">
      <div className="flex items-center gap-2">
        <Label className="text-[10px] uppercase tracking-wide text-muted-foreground">
          Etiqueta
        </Label>
        <Input
          value={variant.label}
          onChange={(e) => onChange({ label: e.target.value })}
          className="h-7 flex-1 text-xs"
          placeholder="v1"
        />
        {onRemove && (
          <button
            type="button"
            aria-label="Eliminar variante"
            onClick={onRemove}
            className="rounded p-1 text-muted-foreground hover:text-red-600"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {variant.patches.length === 0 && (
        <p className="rounded border border-dashed border-border/60 px-3 py-3 text-center text-[11px] text-muted-foreground">
          Sin cambios — esta variante sería un duplicado exacto del base.
        </p>
      )}

      <div className="space-y-2">
        {variant.patches.map((p, idx) => {
          const usedByOthers = new Set(
            variant.patches.filter((_, i) => i !== idx).map((q) => q.field),
          );
          const fieldOptions = applicableFields.filter(
            (f) => f === p.field || !usedByOthers.has(f),
          );
          return (
            <div key={idx} className="grid grid-cols-[1fr_1fr_auto] items-center gap-2">
              <select
                className={SELECT_CLASS}
                value={p.field}
                onChange={(e) =>
                  // Different field → different value kind, so clear the value.
                  updatePatch(idx, {
                    field: e.target.value as AxisField,
                    value: null,
                  })
                }
              >
                {fieldOptions.map((f) => (
                  <option key={f} value={f}>
                    {AXIS_LABELS[f]}
                  </option>
                ))}
              </select>
              <AxisSingleValueEditor
                field={p.field}
                value={p.value}
                onChange={(value) => updatePatch(idx, { value })}
                catalogues={catalogues}
              />
              <button
                type="button"
                aria-label="Quitar override"
                onClick={() => removePatch(idx)}
                className="rounded p-1.5 text-muted-foreground hover:text-red-600"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          );
        })}
      </div>

      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={addPatch}
        disabled={variant.patches.length >= applicableFields.length}
      >
        <Plus className="mr-1 h-3 w-3" /> Añadir override
      </Button>
    </div>
  );
}

function RadioRow({
  current,
  value,
  label,
  onChange,
}: {
  current: ApplyMode;
  value: ApplyMode;
  label: string;
  onChange: (next: ApplyMode) => void;
}) {
  return (
    <label className="flex items-center gap-2">
      <input
        type="radio"
        checked={current === value}
        onChange={() => onChange(value)}
      />
      <span>{label}</span>
    </label>
  );
}
