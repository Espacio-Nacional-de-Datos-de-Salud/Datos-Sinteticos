"use client";

// Modal shown before launching a job (inspection, training, generation,
// evaluation). Lets the user give the run a functional name up front; the
// field is optional — leaving it blank keeps the auto-generated name.

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function NamePromptDialog({
  open,
  title,
  description,
  placeholder = "Nombre (opcional)",
  confirmLabel = "Iniciar",
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  description: string;
  placeholder?: string;
  confirmLabel?: string;
  /** Receives the trimmed name (empty string when left blank). */
  onConfirm: (name: string) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");

  if (!open) return null;

  const confirm = () => {
    onConfirm(name.trim());
    setName("");
  };
  const cancel = () => {
    setName("");
    onCancel();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={cancel}
    >
      <div
        className="w-full max-w-sm rounded-lg border bg-background p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-2 text-base font-semibold">{title}</h2>
        <p className="mb-4 text-sm text-muted-foreground">{description}</p>
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={placeholder}
          autoFocus
          onKeyDown={(e) => {
            if (e.key === "Enter") confirm();
            if (e.key === "Escape") cancel();
          }}
          className="mb-6"
        />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={cancel}>
            Cancelar
          </Button>
          <Button type="button" size="sm" onClick={confirm}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
