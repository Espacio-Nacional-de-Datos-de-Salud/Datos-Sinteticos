import * as React from "react";

import { cn } from "@/lib/utils";

type WorkflowGroupProps = React.ComponentProps<"section"> & {
  label: string;
};

function WorkflowGroup({ label, className, children, ...props }: WorkflowGroupProps) {
  return (
    <section
      className={cn(
        "relative rounded-lg border border-border/80 bg-muted/20 p-3 pl-4 shadow-sm",
        "before:absolute before:inset-y-3 before:left-0 before:w-1 before:rounded-r-full before:bg-primary/60",
        className,
      )}
      {...props}
    >
      <div className="mb-3 flex items-center gap-2 px-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        <span className="h-px w-5 bg-primary/50" />
        <span>{label}</span>
      </div>
      <div className="space-y-4">{children}</div>
    </section>
  );
}

export { WorkflowGroup };
