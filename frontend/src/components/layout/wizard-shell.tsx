// Bottom-of-page wizard navigation: Anterior / dots / Siguiente.
//
// Each pipeline step page wraps its content in <WizardShell currentSlug=…>.
// The shell figures out prev/next from PIPELINE_STEPS and renders the nav.
// Pages pass `canAdvance` to gate the Siguiente button (e.g. Ingesta only
// lets you advance once an inspection has completed).

"use client";

import Link from "next/link";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { PIPELINE_STEPS, findStepIndex, stepHref } from "@/lib/pipeline-steps";
import { cn } from "@/lib/utils";

export function WizardShell({
  currentSlug,
  canAdvance = true,
  children,
}: {
  currentSlug: string;
  canAdvance?: boolean;
  children: React.ReactNode;
}) {
  const index = findStepIndex(currentSlug);
  const prev = index > 0 ? PIPELINE_STEPS[index - 1] : null;
  const next = index < PIPELINE_STEPS.length - 1 ? PIPELINE_STEPS[index + 1] : null;

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-auto px-8 py-6">{children}</div>

      <div className="flex items-center justify-between border-t bg-background px-8 py-4">
        {prev ? (
          <Link
            href={stepHref(prev)}
            className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
          >
            <ChevronLeft className="h-4 w-4" />
            Anterior
          </Link>
        ) : (
          <span />
        )}

        <div className="flex gap-1.5">
          {PIPELINE_STEPS.map((s, i) => (
            <span
              key={s.slug}
              className={cn(
                "h-1.5 rounded-full transition-all",
                i === index ? "w-6 bg-primary" : "w-1.5 bg-muted",
              )}
            />
          ))}
        </div>

        {next ? (
          <Link
            href={canAdvance ? stepHref(next) : "#"}
            aria-disabled={!canAdvance}
            className={cn(
              "inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium",
              canAdvance
                ? "bg-[#00215C] text-white hover:bg-[#04214d]"
                : "pointer-events-none cursor-not-allowed bg-muted text-muted-foreground",
            )}
          >
            Siguiente Paso
            <ChevronRight className="h-4 w-4" />
          </Link>
        ) : (
          <span />
        )}
      </div>
    </div>
  );
}
