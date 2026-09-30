"use client";

// Shown when a delete is refused because the artifact still has downstream
// jobs. Unlike ConfirmDialog this offers three choices: cascade (delete the
// downstream artifacts too), force (delete anyway, leaving them orphaned), or
// cancel.

import { Button } from "@/components/ui/button";

export function DeleteConflictDialog({
  open,
  message,
  onCascade,
  onForce,
  onCancel,
}: {
  open: boolean;
  message: string;
  onCascade: () => void;
  onForce: () => void;
  onCancel: () => void;
}) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-md rounded-lg border bg-background p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-2 text-base font-semibold">
          No se puede eliminar directamente
        </h2>
        <p className="mb-6 text-sm text-muted-foreground">
          {message} ¿Cómo deseas continuar?
        </p>
        <div className="flex flex-col gap-2">
          <Button
            type="button"
            variant="destructive"
            size="sm"
            onClick={onCascade}
          >
            Eliminar con sus dependencias
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={onForce}>
            Eliminar de todos modos (dejar dependencias huérfanas)
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
            Cancelar
          </Button>
        </div>
      </div>
    </div>
  );
}
