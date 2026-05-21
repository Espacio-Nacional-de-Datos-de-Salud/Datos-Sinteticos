"use client";

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ChevronDown } from "lucide-react";
import * as YAML from "js-yaml";
import { api, type ConfigContent } from "@/lib/api";
import { useApplyModePreset } from "@/hooks/use-apply-mode-preset";

export type ModeType = "privacy" | "balanced" | "utility";

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
}

export function ModeSelector({ selectedMode, onModeSelected, onApplyMode }: ModeSelectorProps) {
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
        // Use defaults if config doesn't exist
        const defaults: Record<ModeType, ModePreset> = {
          privacy: {
            label: "Privacidad",
            description: "Privacidad máxima con modelo pequeño",
            details: [
              "Modelo pequeño para reducir riesgo de fuga",
              "Privacidad diferencial robusta (ε=1.0)",
              "Utilidad reducida pero máxima protección",
            ],
            icon: "🔒",
            config: {
              model_settings: {
                model: "MOSTLY_AI/Small",
                batch_size: 16,
                enable_flexible_generation: false,
              },
              differential_privacy: {
                max_epsilon: 1.0,
                noise_multiplier: 2.0,
              },
            },
          },
          balanced: {
            label: "Equilibrado",
            description: "Balance recomendado entre privacidad y utilidad",
            details: [
              "Modelo mediano para buena utilidad",
              "Flexible generation habilitada",
              "Configuración recomendada para la mayoría de casos",
            ],
            icon: "⚖️",
            config: {
              model_settings: {
                model: "MOSTLY_AI/Medium",
                batch_size: 16,
                enable_flexible_generation: true,
              },
            },
          },
          utility: {
            label: "Utilidad",
            description: "Máxima calidad sintética con privacidad mínima",
            details: [
              "Modelo grande para mejor síntesis",
              "Privacidad diferencial mínima",
              "Mejor calidad sintética pero menor privacidad",
              "Útil para datos no sensibles",
            ],
            icon: "✨",
            config: {
              model_settings: {
                model: "MOSTLY_AI/Large",
                batch_size: 32,
                enable_flexible_generation: true,
              },
            },
          },
        };
        setModes(defaults);
      }
    };
    loadModes();
  }, []);

  const handleSelectMode = async (mode: ModeType) => {
    if (!modes) return;

    onModeSelected?.(mode);

    try {
      const { data } = await api.get<{ content: string }>("/configs/mode_presets");
      const parsed = YAML.load(data.content) as ModesConfig | null;
      if (parsed?.modes?.[mode]?.["config"]) {
        const config = (parsed.modes[mode] as any).config;
        await applyPresetMutation.mutateAsync(config);
        // Force a fresh fetch from the server
        await queryClient.ensureQueryData({
          queryKey: ["config", "mostly_ai"],
          queryFn: async () => {
            const { data } = await api.get<ConfigContent>("/configs/mostly_ai");
            return data;
          }
        });
        onApplyMode?.();
      }
    } catch (err) {
      console.error("Error applying mode:", err);
      toast.error("Error al aplicar el modo");
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
