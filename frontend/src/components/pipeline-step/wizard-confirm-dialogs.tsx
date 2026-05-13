"use client";

// Three ConfirmDialogs bundled together because every wizard-step page
// renders the same trio (delete / cleanup / purge) with only the strings
// differing per kind. Pages own the boolean state and the confirm handlers;
// this component just wires the matching props into three dialogs.

import { ConfirmDialog } from "@/components/ui/confirm-dialog";

export type WizardConfirmTexts = {
  delete: {
    title: string;
    description: string;
    confirmLabel?: string;
  };
  cleanup: {
    title: string;
    description: string;
    confirmLabel?: string;
  };
  purge: {
    title: string;
    description: string;
    confirmLabel?: string;
  };
};

export function WizardConfirmDialogs({
  texts,
  confirmDeleteId,
  setConfirmDeleteId,
  onDelete,
  confirmCleanup,
  setConfirmCleanup,
  onCleanup,
  confirmPurge,
  setConfirmPurge,
  onPurge,
}: {
  texts: WizardConfirmTexts;
  confirmDeleteId: string | null;
  setConfirmDeleteId: (id: string | null) => void;
  onDelete: (id: string) => void;
  confirmCleanup: boolean;
  setConfirmCleanup: (open: boolean) => void;
  onCleanup: () => void;
  confirmPurge: boolean;
  setConfirmPurge: (open: boolean) => void;
  onPurge: () => void;
}) {
  return (
    <>
      <ConfirmDialog
        open={confirmDeleteId !== null}
        title={texts.delete.title}
        description={texts.delete.description}
        confirmLabel={texts.delete.confirmLabel ?? "Eliminar"}
        onConfirm={() => {
          if (confirmDeleteId) onDelete(confirmDeleteId);
          setConfirmDeleteId(null);
        }}
        onCancel={() => setConfirmDeleteId(null)}
      />
      <ConfirmDialog
        open={confirmCleanup}
        title={texts.cleanup.title}
        description={texts.cleanup.description}
        confirmLabel={texts.cleanup.confirmLabel ?? "Limpiar"}
        onConfirm={() => {
          onCleanup();
          setConfirmCleanup(false);
        }}
        onCancel={() => setConfirmCleanup(false)}
      />
      <ConfirmDialog
        open={confirmPurge}
        title={texts.purge.title}
        description={texts.purge.description}
        confirmLabel={texts.purge.confirmLabel ?? "Purgar"}
        onConfirm={() => {
          onPurge();
          setConfirmPurge(false);
        }}
        onCancel={() => setConfirmPurge(false)}
      />
    </>
  );
}
