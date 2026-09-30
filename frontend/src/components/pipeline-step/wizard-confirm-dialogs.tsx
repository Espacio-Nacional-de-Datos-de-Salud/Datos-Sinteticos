"use client";

// Three ConfirmDialogs bundled together because every wizard-step page
// renders the same trio (delete / cleanup / purge) with only the strings
// differing per kind. Pages own the boolean state and the confirm handlers;
// this component just wires the matching props into three dialogs.

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { DeleteConflictDialog } from "@/components/pipeline-step/delete-conflict-dialog";
import { PurgeChoiceDialog } from "@/components/pipeline-step/purge-choice-dialog";
import type { DeleteConflictState } from "@/components/pipeline-step/use-artifact-lifecycle";

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
    /** Shown only on the cascade variant (when onPurgeCascade is provided). */
    cascadeLabel?: string;
    orphanLabel?: string;
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
  onPurgeCascade,
  deleteConflict,
  onDeleteConflictCascade,
  onDeleteConflictForce,
  onDeleteConflictDismiss,
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
  /** Purge only this step, orphaning downstream artifacts. */
  onPurge: () => void;
  /** When provided, the purge dialog offers a cascade-or-orphan choice. */
  onPurgeCascade?: () => void;
  /** Conflict state from useArtifactLifecycle; null hides the conflict dialog. */
  deleteConflict?: DeleteConflictState | null;
  onDeleteConflictCascade?: () => void;
  onDeleteConflictForce?: () => void;
  onDeleteConflictDismiss?: () => void;
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
      {onPurgeCascade ? (
        <PurgeChoiceDialog
          open={confirmPurge}
          title={texts.purge.title}
          description={texts.purge.description}
          cascadeLabel={texts.purge.cascadeLabel ?? "Purgar con sus dependencias"}
          orphanLabel={texts.purge.orphanLabel ?? "Purgar solo este paso (dejar huérfanas)"}
          onCascade={() => {
            onPurgeCascade();
            setConfirmPurge(false);
          }}
          onOrphan={() => {
            onPurge();
            setConfirmPurge(false);
          }}
          onCancel={() => setConfirmPurge(false)}
        />
      ) : (
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
      )}
      <DeleteConflictDialog
        open={deleteConflict != null}
        message={deleteConflict?.message ?? ""}
        onCascade={() => onDeleteConflictCascade?.()}
        onForce={() => onDeleteConflictForce?.()}
        onCancel={() => onDeleteConflictDismiss?.()}
      />
    </>
  );
}
