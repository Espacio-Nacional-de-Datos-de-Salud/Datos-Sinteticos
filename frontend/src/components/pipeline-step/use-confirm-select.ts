"use client";

// Selecting a past run from a step's history is a "view what was already done"
// action, distinct from the "prepare a new run" form above it. Jumping to a
// past run therefore loads its results AND discards whatever the user was
// setting up — so we gate the jump behind a confirmation dialog.
//
// Each page passes an `onConfirm(id)` that does both: select the run as the
// page's active one (filling the Resultados section) and reset its Preparación
// form to defaults. This hook only owns the pending-id + confirm/cancel
// plumbing so every page wires the same dialog the same way.

import { useState } from "react";

export function useConfirmSelect(
  onConfirm: (id: string) => void,
  /** Currently active run; re-selecting it is a no-op (skips the dialog). */
  currentId: string | null,
) {
  const [pendingId, setPendingId] = useState<string | null>(null);

  return {
    /** The run pending confirmation, or null when the dialog is closed. */
    pendingId,
    /** Ask to switch to `id`; opens the dialog unless it's already active. */
    request: (id: string) => {
      if (id && id !== currentId) setPendingId(id);
    },
    confirm: () => {
      if (pendingId) onConfirm(pendingId);
      setPendingId(null);
    },
    cancel: () => setPendingId(null),
  };
}
