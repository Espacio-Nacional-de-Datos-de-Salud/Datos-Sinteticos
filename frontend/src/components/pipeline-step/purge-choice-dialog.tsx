"use client";

// Shown when the user purges *all* sessions of a step that has downstream
// artifacts. Unlike a plain ConfirmDialog this offers three choices: cascade
// (also delete every downstream artifact so nothing is orphaned), orphan
// (delete only this step, leaving dependents behind), or cancel. Mirrors the
// per-item DeleteConflictDialog so the two destructive flows feel consistent.

import { Button } from "@/components/ui/button";

export function PurgeChoiceDialog({
  open,
  title,
  description,
  cascadeLabel,
  orphanLabel,
  onCascade,
  onOrphan,
  onCancel,
}: {
  open: boolean;
  title: string;
  description: string;
  cascadeLabel: string;
  orphanLabel: string;
  onCascade: () => void;
  onOrphan: () => void;
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
        <h2 className="mb-2 text-base font-semibold">{title}</h2>
        <p className="mb-6 text-sm text-muted-foreground">{description}</p>
        <div className="flex flex-col gap-2">
          <Button type="button" variant="destructive" size="sm" onClick={onCascade}>
            {cascadeLabel}
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={onOrphan}>
            {orphanLabel}
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
            Cancelar
          </Button>
        </div>
      </div>
    </div>
  );
}
