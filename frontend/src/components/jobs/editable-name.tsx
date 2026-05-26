"use client";

import { useState } from "react";
import { Pencil } from "lucide-react";
import { toast } from "sonner";

export function EditableName({
  name,
  existingNames = [],
  onSave,
  size = "xs",
}: {
  name: string;
  existingNames?: string[];
  onSave: (name: string) => Promise<void>;
  /** Text size of the displayed name. Banners use "sm"; lists keep "xs". */
  size?: "xs" | "sm";
}) {
  const textSize = size === "sm" ? "text-sm" : "text-xs";
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(name);
  const [saving, setSaving] = useState(false);

  const save = async () => {
    const trimmed = value.trim();
    if (!trimmed || trimmed === name) {
      setEditing(false);
      setValue(name);
      return;
    }
    const isDuplicate = existingNames.some(
      (n) => n.toLowerCase() === trimmed.toLowerCase() && n !== name,
    );
    if (isDuplicate) {
      toast.warning(`El nombre "${trimmed}" ya está en uso por otra ejecución.`);
    }
    setSaving(true);
    try {
      await onSave(trimmed);
    } finally {
      setSaving(false);
      setEditing(false);
    }
  };

  if (editing) {
    return (
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={save}
        onKeyDown={(e) => {
          if (e.key === "Enter") save();
          if (e.key === "Escape") {
            setEditing(false);
            setValue(name);
          }
        }}
        disabled={saving}
        autoFocus
        className={`w-full rounded border border-border bg-background px-1 py-0.5 ${textSize} font-mono focus:outline-none focus:ring-1 focus:ring-ring`}
        onClick={(e) => e.stopPropagation()}
      />
    );
  }

  return (
    <span
      className="group flex cursor-pointer items-center gap-1.5 rounded px-1 py-0.5 transition-colors hover:bg-accent/50"
      onClick={(e) => {
        e.stopPropagation();
        setEditing(true);
        setValue(name);
      }}
      title="Haz clic para editar el nombre"
    >
      <span className={`truncate font-mono ${textSize}`}>{name}</span>
      <Pencil className="h-4 w-4 shrink-0 text-muted-foreground transition-colors group-hover:text-foreground" />
    </span>
  );
}
