"use client";

import { useEffect, useState } from "react";
import { Settings, Info } from "lucide-react";
import { toast } from "sonner";
import * as YAML from "js-yaml";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";

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

interface ModePresetsProps {
  onSelectMode: (mode: ModeType, config: Record<string, unknown>) => void;
  selectedMode?: ModeType;
  onModeApplied?: () => void;
}

export function ModePresets({ onSelectMode, selectedMode, onModeApplied }: ModePresetsProps) {
  const [modes, setModes] = useState<Record<ModeType, ModePreset> | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [expandedMode, setExpandedMode] = useState<ModeType | null>(null);

  useEffect(() => {
    const loadModes = async () => {
      try {
        const { data } = await api.get<{ content: string }>("/configs/mode_presets");
        // Parse YAML content
        const parsed = YAML.load(data.content) as ModesConfig | null;
        if (parsed?.modes) {
          setModes(parsed.modes);
        } else {
          throw new Error("Invalid mode_presets format");
        }
      } catch (err) {
        // Fallback to defaults if config doesn't exist
        const defaults: Record<ModeType, ModePreset> = {
          privacy: {
            label: "Modo Privacidad",
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
            label: "Modo Equilibrado",
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
            label: "Modo Utilidad",
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
      } finally {
        setIsLoading(false);
      }
    };
    loadModes();
  }, []);

  const handleSelectMode = (mode: ModeType) => {
    if (!modes) return;
    onSelectMode(mode, modes[mode].config);
    toast.success(`Preset "${modes[mode].label}" aplicado`);
    onModeApplied?.();
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Settings className="h-4 w-4" />
            <div>
              <CardTitle className="text-base">Modos de configuración</CardTitle>
              <CardDescription>Cargando presets...</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-32 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (!modes) return null;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between">
          <div className="flex gap-3 flex-1">
            <Settings className="h-5 w-5 mt-0.5 text-primary" />
            <div className="flex-1 min-w-0">
              <CardTitle className="text-base">Modos de configuración predefinidos</CardTitle>
              <CardDescription>
                Elige un preset o personaliza manualmente en la sección de abajo
              </CardDescription>
            </div>
          </div>
          <Info className="h-4 w-4 text-muted-foreground flex-shrink-0 mt-1" />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
          {(Object.entries(modes) as Array<[ModeType, ModePreset]>).map(([modeKey, mode]) => (
            <div
              key={modeKey}
              className={`rounded-lg border p-3 transition-colors cursor-pointer ${
                selectedMode === modeKey
                  ? "border-primary bg-primary/5"
                  : "border-border hover:border-primary/50 hover:bg-muted/30"
              }`}
              onClick={() => handleSelectMode(modeKey)}
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <span className="text-2xl">{mode.icon}</span>
                {selectedMode === modeKey && (
                  <span className="text-xs font-semibold text-primary px-2 py-1 rounded bg-primary/10">
                    ✓ Activo
                  </span>
                )}
              </div>
              <h4 className="font-semibold text-sm mb-1">{mode.label}</h4>
              <p className="text-xs text-muted-foreground mb-3 line-clamp-2">{mode.description}</p>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setExpandedMode(expandedMode === modeKey ? null : modeKey);
                }}
                className="text-xs text-primary hover:underline font-medium"
              >
                {expandedMode === modeKey ? "- Ocultar" : "+ Detalles"}
              </button>
              {expandedMode === modeKey && (
                <ul className="mt-3 space-y-1.5 text-[11px] text-muted-foreground border-t pt-3">
                  {mode.details.map((detail, idx) => (
                    <li key={idx} className="flex gap-2">
                      <span className="text-primary">•</span>
                      <span>{detail}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
