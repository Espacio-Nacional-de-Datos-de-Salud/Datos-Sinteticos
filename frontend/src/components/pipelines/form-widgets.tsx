"use client";

// Tiny dropdowns shared by JobCard. Built on the shared <NativeSelect> wrapper
// (Base UI Select) rather than promoted to a generic <MultiSelect/>: the page
// only needs two flavours and a real combobox would be overkill here.

import { X } from "lucide-react";

import { NativeSelect } from "@/components/ui/native-select";
import type { DataFile, InspectionSummary } from "@/lib/api";

export function FilesMultiSelect({
  files,
  selected,
  onChange,
  placeholder = "Añade archivos…",
}: {
  files: DataFile[];
  selected: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
}) {
  const remaining = files.filter((f) => !selected.includes(f.path));
  return (
    <div className="space-y-2">
      {selected.length > 0 && (
        <ul className="space-y-1">
          {selected.map((path) => (
            <li
              key={path}
              className="flex items-center justify-between gap-2 rounded-md border border-border bg-muted/30 px-2.5 py-1.5 text-xs"
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
      <NativeSelect
        className="h-9"
        value=""
        onValueChange={(next) => {
          if (next) onChange([...selected, next]);
        }}
      >
        <option value="">{placeholder}</option>
        {remaining.map((f) => (
          <option key={f.path} value={f.path}>
            {f.name}
          </option>
        ))}
      </NativeSelect>
    </div>
  );
}

export function InspectionSelect({
  inspections,
  value,
  onChange,
}: {
  inspections: InspectionSummary[];
  value: string;
  onChange: (next: string) => void;
}) {
  return (
    <NativeSelect
      className="h-9"
      value={value}
      onValueChange={onChange}
    >
      <option value="">Selecciona una inspección…</option>
      {inspections.map((i) => (
        <option key={i.inspection_id} value={i.inspection_id}>
          {i.inspection_name || i.inspection_id}
        </option>
      ))}
    </NativeSelect>
  );
}
