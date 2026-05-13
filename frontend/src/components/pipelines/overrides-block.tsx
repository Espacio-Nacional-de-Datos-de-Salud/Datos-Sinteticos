"use client";

// Per-job overrides editor — collapsible. Only the keys explicitly set by the
// user end up in the YAML (deep-merge semantics on the backend); empty fields
// inherit the global defaults from mostly_ai.yaml / general.yaml.

import { useState } from "react";
import { Settings } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { MOSTLY_AI_MODELS, type JobOverrides } from "@/components/pipelines/types";
import type { ConfigFile } from "@/lib/api";
import { SELECT_CLASS } from "@/lib/ui";

const TRI_OPTIONS: { value: "" | "true" | "false"; label: string }[] = [
  { value: "", label: "Por defecto" },
  { value: "true", label: "Activado" },
  { value: "false", label: "Desactivado" },
];

export function OverridesBlock({
  overrides,
  rulesConfigs,
  overrideCount,
  setOverride,
  onEditRules,
}: {
  overrides: JobOverrides;
  rulesConfigs: ConfigFile[];
  overrideCount: number;
  setOverride: <K extends keyof JobOverrides>(key: K, val: JobOverrides[K]) => void;
  onEditRules: (id: string) => void;
}) {
  const [open, setOpen] = useState(overrideCount > 0);
  return (
    <div className="rounded-md border border-border bg-background">
      <button
        type="button"
        className="flex w-full items-center justify-between px-3 py-2 text-left"
        onClick={() => setOpen((v) => !v)}
      >
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-bold uppercase tracking-[0.08em] text-muted-foreground">
            Overrides (opcional)
          </span>
          {overrideCount > 0 && (
            <span className="rounded-full bg-[#FFDB00] px-1.5 py-0.5 text-[10px] font-bold text-[#00215C]">
              {overrideCount} {overrideCount === 1 ? "ajuste" : "ajustes"}
            </span>
          )}
        </div>
        <span className="text-xs text-muted-foreground">{open ? "▾" : "▸"}</span>
      </button>

      {open && (
        <div className="space-y-4 border-t border-border p-3">
          {/* Reglas dedicadas — apuntan a un YAML del scope `rules`. Permite
              que el usuario defina constraints específicos para este job sin
              tocar el archivo global. */}
          <div className="space-y-1">
            <div className="flex items-center justify-between gap-2">
              <Label className="text-xs">Configuración de reglas</Label>
              <button
                type="button"
                onClick={() => {
                  const val = overrides.rules_config;
                  const id = val.startsWith("config/") ? val.slice(7) : "rules";
                  onEditRules(id);
                }}
                className="flex items-center gap-1 text-[10px] font-semibold text-muted-foreground transition-colors hover:text-foreground"
              >
                <Settings className="h-3 w-3" />
                {overrides.rules_config ? "Editar selección" : "Editar reglas globales"}
              </button>
            </div>
            <select
              className={SELECT_CLASS}
              value={overrides.rules_config}
              onChange={(e) => setOverride("rules_config", e.target.value)}
            >
              <option value="">Usar reglas globales (rules.yaml)</option>
              {rulesConfigs.map((r) => (
                <option key={r.id} value={`config/${r.id}`}>
                  {r.id}
                </option>
              ))}
            </select>
          </div>

          {/* Mostly AI — model_settings.* */}
          <div className="rounded border border-border/60 p-3">
            <div className="mb-2 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
              Mostly AI · model_settings
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Modelo</Label>
                <select
                  className={SELECT_CLASS}
                  value={overrides.model}
                  onChange={(e) => setOverride("model", e.target.value)}
                >
                  <option value="">Por defecto</option>
                  {MOSTLY_AI_MODELS.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">max_epochs</Label>
                <Input
                  type="number"
                  min={1}
                  placeholder="por defecto"
                  value={overrides.max_epochs}
                  onChange={(e) => setOverride("max_epochs", e.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">batch_size</Label>
                <Input
                  type="number"
                  min={1}
                  placeholder="por defecto"
                  value={overrides.batch_size}
                  onChange={(e) => setOverride("batch_size", e.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">enable_flexible_generation</Label>
                <select
                  className={SELECT_CLASS}
                  value={overrides.enable_flexible_generation}
                  onChange={(e) =>
                    setOverride(
                      "enable_flexible_generation",
                      e.target.value as "" | "true" | "false",
                    )
                  }
                >
                  {TRI_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">enable_model_report</Label>
                <select
                  className={SELECT_CLASS}
                  value={overrides.enable_model_report}
                  onChange={(e) =>
                    setOverride(
                      "enable_model_report",
                      e.target.value as "" | "true" | "false",
                    )
                  }
                >
                  {TRI_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Differential privacy — leaving both empty keeps DP off (or
                whatever the global config has). Filling them turns it on. */}
            <div className="mt-3 rounded border border-dashed border-border/60 p-2.5">
              <div className="mb-2 text-[10px] font-bold uppercase tracking-wide text-muted-foreground">
                differential_privacy (opcional)
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label className="text-xs">max_epsilon</Label>
                  <Input
                    type="number"
                    step="0.1"
                    min={0}
                    placeholder="—"
                    value={overrides.dp_max_epsilon}
                    onChange={(e) => setOverride("dp_max_epsilon", e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">noise_multiplier</Label>
                  <Input
                    type="number"
                    step="0.1"
                    min={0}
                    placeholder="—"
                    value={overrides.dp_noise_multiplier}
                    onChange={(e) => setOverride("dp_noise_multiplier", e.target.value)}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* General — settings.* */}
          <div className="rounded border border-border/60 p-3">
            <div className="mb-2 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
              General
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">enable_data_profiling</Label>
                <select
                  className={SELECT_CLASS}
                  value={overrides.enable_data_profiling}
                  onChange={(e) =>
                    setOverride(
                      "enable_data_profiling",
                      e.target.value as "" | "true" | "false",
                    )
                  }
                >
                  {TRI_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">default_csv_delimiter</Label>
                <Input
                  placeholder="por defecto (,)"
                  maxLength={3}
                  value={overrides.default_csv_delimiter}
                  onChange={(e) => setOverride("default_csv_delimiter", e.target.value)}
                />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
