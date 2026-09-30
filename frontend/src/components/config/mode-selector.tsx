"use client";

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ChevronDown, Gauge, Rabbit, Turtle } from "lucide-react";
import * as YAML from "js-yaml";
import { api, type ConfigContent } from "@/lib/api";
import { useApplyModePreset } from "@/hooks/use-apply-mode-preset";
import { adaptiveBatchSize, type BatchSpeed } from "@/lib/batch-size";
import { Tooltip } from "@/components/ui/tooltip";

export type ModeType = "privacy" | "balanced" | "utility" | "free";

// Size the preset's training batch to the selected dataset (when its row count
// is known) instead of using the fixed value baked into the preset YAML. The
// batch is independent of the privacy mode; the speed control decides the curve.
function withAdaptiveBatch(
  config: Record<string, unknown>,
  speed: BatchSpeed,
  rowCount?: number,
): Record<string, unknown> {
  if (rowCount == null) return config;
  const ms = config.model_settings;
  if (!ms || typeof ms !== "object" || Array.isArray(ms)) return config;
  return {
    ...config,
    model_settings: {
      ...(ms as Record<string, unknown>),
      batch_size: adaptiveBatchSize(rowCount, speed),
    },
  };
}

const SPEED_OPTIONS: Array<{ value: BatchSpeed; label: string; icon: typeof Gauge; title: string }> = [
  {
    value: "slow",
    label: "Más preciso",
    icon: Turtle,
    title: "Batches menores: el modelo ajusta más veces sobre los mismos datos → aprende mejor (más preciso), pero entrena más lento.",
  },
  {
    value: "balanced",
    label: "Equilibrado",
    icon: Gauge,
    title: "Tamaño de batch equilibrado para tus datos: compromiso entre precisión y tiempo de entrenamiento.",
  },
  {
    value: "fast",
    label: "Más rápido",
    icon: Rabbit,
    title: "Batches mayores: el modelo ajusta menos veces sobre los mismos datos → aprende menos, pero entrena más rápido.",
  },
];

interface ModePreset {
  label: string;
  description: string;
  details: string[];
  icon: string;
  config: Record<string, unknown>;
}

interface ModesConfig {
  modes: Record<ModeType, ModePreset>;
}

interface ModeSelectorProps {
  selectedMode?: ModeType;
  onModeSelected?: (mode: ModeType) => void;
  onApplyMode?: () => void;
  /** Row count of the selected upstream dataset; when set, the preset's batch
      size is auto-sized to it (largest table) instead of the fixed YAML value. */
  presetRowCount?: number;
  /** Training-speed selection driving the batch size (independent of the mode). */
  selectedSpeed?: BatchSpeed;
  onSpeedSelected?: (speed: BatchSpeed) => void;
}

export function ModeSelector({
  selectedMode,
  onModeSelected,
  onApplyMode,
  presetRowCount,
  selectedSpeed = "balanced",
  onSpeedSelected,
}: ModeSelectorProps) {
  const [modes, setModes] = useState<Record<ModeType, ModePreset> | null>(null);
  const [expandedMode, setExpandedMode] = useState<ModeType | null>(null);
  const queryClient = useQueryClient();
  const applyPresetMutation = useApplyModePreset();

  useEffect(() => {
    const loadModes = async () => {
      try {
        const { data } = await api.get<{ content: string }>("/configs/mode_presets");
        const parsed = YAML.load(data.content) as ModesConfig | null;
        if (parsed?.modes) {
          setModes(parsed.modes);
        }
      } catch (err) {
        console.error("No se pudo cargar mode_presets.yaml:", err);
      }
    };
    loadModes();
  }, []);

  // Persist the freshly merged config back, then force a refetch so the form
  // reflects it. Shared by mode selection and speed selection.
  const refreshConfig = async () => {
    await queryClient.ensureQueryData({
      queryKey: ["config", "mostly_ai"],
      queryFn: async () => {
        const { data } = await api.get<ConfigContent>("/configs/mostly_ai");
        return data;
      },
    });
    onApplyMode?.();
  };

  const handleSelectMode = async (mode: ModeType) => {
    if (!modes) return;

    onModeSelected?.(mode);

    try {
      const { data } = await api.get<{ content: string }>("/configs/mode_presets");
      const parsed = YAML.load(data.content) as ModesConfig | null;
      if (parsed?.modes?.[mode]?.["config"]) {
        const config = parsed.modes[mode].config;
        await applyPresetMutation.mutateAsync(withAdaptiveBatch(config, selectedSpeed, presetRowCount));
        await refreshConfig();
      }
    } catch (err) {
      console.error("Error applying mode:", err);
      toast.error("Error al aplicar el modo");
    }
  };

  // Speed only drives the (locked) batch size under an active preset; in "Libre"
  // the batch is hand-edited, so the control is hidden.
  const showSpeed = presetRowCount != null && !!selectedMode && selectedMode !== "free";

  const handleSelectSpeed = async (speed: BatchSpeed) => {
    onSpeedSelected?.(speed);
    if (!showSpeed || presetRowCount == null) return;
    try {
      await applyPresetMutation.mutateAsync({
        model_settings: { batch_size: adaptiveBatchSize(presetRowCount, speed) },
      });
      await refreshConfig();
    } catch (err) {
      console.error("Error applying speed:", err);
      toast.error("Error al ajustar la velocidad");
    }
  };

  if (!modes) return null;

  return (
    <div className="space-y-2">
      <div className="flex gap-1.5">
        {(Object.entries(modes) as Array<[ModeType, ModePreset]>).map(([modeKey, mode]) => (
          <button
            key={modeKey}
            type="button"
            onClick={() => handleSelectMode(modeKey)}
            title={mode.description}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
              selectedMode === modeKey
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground hover:bg-muted hover:text-foreground"
            }`}
          >
            <span className="text-base">{mode.icon}</span>
            <span className="hidden sm:inline">{mode.label}</span>
          </button>
        ))}
      </div>
      {showSpeed && (
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1 text-[11px] font-medium text-muted-foreground">
            Precisión / velocidad:
            <Tooltip
              content="El batch se ajusta solo al número de filas de tus datos; aquí decides el equilibrio precisión/tiempo. En casos extremos puede no variar: con muy pocos datos se queda en el mínimo y con muchísimos en el máximo."
              side="top"
            />
          </span>
          <div className="inline-flex rounded-md border bg-background p-0.5">
            {SPEED_OPTIONS.map((opt) => {
              const active = selectedSpeed === opt.value;
              const Icon = opt.icon;
              return (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => handleSelectSpeed(opt.value)}
                  title={opt.title}
                  className={`flex items-center gap-1 rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                    active
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:bg-muted"
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  <span className="hidden sm:inline">{opt.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}
      {selectedMode && modes[selectedMode] && (
        <div className="rounded-md border p-2 bg-muted/50">
          <button
            onClick={() => setExpandedMode(expandedMode === selectedMode ? null : selectedMode)}
            className="flex items-center gap-2 w-full text-left text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            <ChevronDown
              className={`h-3.5 w-3.5 transition-transform ${expandedMode === selectedMode ? "rotate-180" : ""}`}
            />
            Detalles del modo
          </button>
          {expandedMode === selectedMode && (
            <ul className="mt-2 space-y-1 text-[11px] text-muted-foreground border-t pt-2">
              {modes[selectedMode].details?.map((detail, idx) => (
                <li key={idx} className="flex gap-2">
                  <span className="text-primary flex-shrink-0">•</span>
                  <span>{detail}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
