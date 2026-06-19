"use client";

import { EditableName } from "@/components/jobs/editable-name";

// The banner "Nombre … actual:" row, shared by every pipeline page so the
// active-run name reads the same everywhere. Each step says what the name
// belongs to (its phase) and, when no run exists yet, shows an italic
// "aún no iniciada" placeholder instead of hiding the row — so the banner
// always tells the user which run is active, or that none is.
export function ActiveRunName({
  label,
  name,
  placeholder,
  existingNames,
  onSave,
}: {
  /** What the name belongs to, e.g. "del modelo", "de la simulación". */
  label: string;
  /** Current run name, or null when no run is active yet. */
  name: string | null;
  /** Italic text shown when there is no active run,
      e.g. "entrenamiento aún no iniciado". */
  placeholder: string;
  existingNames?: string[];
  onSave?: (name: string) => Promise<void>;
}) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="text-muted-foreground">Nombre {label} actual:</span>
      {name && onSave ? (
        <EditableName
          name={name}
          existingNames={existingNames}
          onSave={onSave}
          size="sm"
        />
      ) : (
        <span className="italic text-muted-foreground">{placeholder}</span>
      )}
    </div>
  );
}
