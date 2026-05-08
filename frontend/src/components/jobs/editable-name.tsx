"use client";

import { useState } from "react";
import { Pencil } from "lucide-react";
import { toast } from "sonner";

export function EditableName({
  name,
  existingNames = [],
  onSave,
}: {
  name: string;
  existingNames?: string[];
  onSave: (name: string) => Promise<void>;
}) {
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
        className="w-full rounded border border-border bg-background px-1 py-0.5 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-ring"
        onClick={(e) => e.stopPropagation()}
      />
    );
  }

  return (
    <span
      className="group flex cursor-pointer items-center gap-1"
      onClick={(e) => {
        e.stopPropagation();
        setEditing(true);
        setValue(name);
      }}
    >
      <span className="truncate font-mono text-xs">{name}</span>
      <Pencil className="h-3 w-3 shrink-0 opacity-0 group-hover:opacity-40" />
    </span>
  );
}
