"use client";

import { ActiveRunName } from "@/components/jobs/active-run-name";
import { WizardBanner } from "@/components/layout/wizard-banner";
import type { InspectionSummary } from "@/lib/api";

// Carga de Datos banner. A thin wrapper around the shared WizardBanner that
// fills the `info` slot with the active-run name (or its not-started
// placeholder), exactly like Entrenamiento / Generación / Auditoría. The
// run's progress and detected tables live in the page body, not here, so the
// top bar stays consistent across every wizard step.
export function InspectionBanner({
  inspectionId,
  inspection,
  existingNames,
  onRename,
  instructionsOpen,
  onOpenManual,
}: {
  inspectionId: string | null;
  inspection: InspectionSummary | undefined;
  existingNames: string[];
  onRename: (id: string, name: string) => void;
  instructionsOpen?: boolean;
  onOpenManual?: () => void;
}) {
  const active = inspectionId && inspection ? inspection : null;

  return (
    <WizardBanner
      title="Carga de Datos"
      subtitle={
        <>
          La carga de datos es el primer paso para generar datos sintéticos:
          analiza los ficheros de origen para detectar automáticamente las{" "}
          <span className="font-medium text-foreground">tablas</span>, las{" "}
          <span className="font-medium text-foreground">
            claves primarias y foráneas
          </span>{" "}
          que las relacionan y el{" "}
          <span className="font-medium text-foreground">tipo de cada columna</span>
          . Después podrás revisar lo detectado, definir reglas de negocio y
          consultar los datos preprocesados.
        </>
      }
      instructionsOpen={instructionsOpen}
      onOpenManual={onOpenManual}
      info={
        <ActiveRunName
          label="de la carga de datos"
          name={active ? active.inspection_name || active.inspection_id : null}
          placeholder="carga de datos aún no iniciada"
          existingNames={existingNames}
          onSave={
            inspectionId ? async (name) => onRename(inspectionId, name) : undefined
          }
        />
      }
    />
  );
}
