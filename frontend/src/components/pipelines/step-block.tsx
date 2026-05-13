// Shared chrome for a single train / simulate / evaluate section inside a
// JobCard: a thin labelled card that gives every step block the same
// surrounding rhythm.

import type { ReactNode } from "react";

export function StepBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-2 rounded-md border border-border bg-background p-3">
      <div className="text-[10px] font-bold uppercase tracking-[0.08em] text-muted-foreground">
        {title}
      </div>
      {children}
    </div>
  );
}
