"use client";

import * as React from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";

type WorkflowGroupProps = React.ComponentProps<"section"> & {
  label: string;
  defaultOpen?: boolean;
};

function WorkflowGroup({
  label,
  className,
  children,
  defaultOpen = true,
  ...props
}: WorkflowGroupProps) {
  const [open, setOpen] = React.useState(defaultOpen);
  const contentId = React.useId();
  const sectionRef = React.useRef<HTMLElement | null>(null);

  const handleToggle = () => {
    setOpen((prev) => {
      const next = !prev;
      if (next && !prev) {
        requestAnimationFrame(() => {
          sectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
        });
      }
      return next;
    });
  };

  return (
    <section
      ref={sectionRef}
      className={cn(
        "relative rounded-lg border border-border/80 bg-muted/20 p-3 pl-4 shadow-sm",
        "before:absolute before:inset-y-3 before:left-0 before:w-1 before:rounded-r-full before:bg-primary/60",
        className,
      )}
      {...props}
    >
      <button
        type="button"
        className="mb-1 flex w-full items-center justify-between gap-3 rounded-md px-1 py-1 text-left text-[11px] font-medium uppercase tracking-wide text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-expanded={open}
        aria-controls={contentId}
        onClick={handleToggle}
      >
        <span className="flex items-center gap-2">
          <span className="h-px w-5 bg-primary/50" />
          <span>{label}</span>
        </span>
        {open ? (
          <ChevronDown className="h-4 w-4 shrink-0" />
        ) : (
          <ChevronRight className="h-4 w-4 shrink-0" />
        )}
      </button>

      {open ? (
        <div id={contentId} className="space-y-4 pt-2">
          {children}
        </div>
      ) : null}
    </section>
  );
}

export { WorkflowGroup };
