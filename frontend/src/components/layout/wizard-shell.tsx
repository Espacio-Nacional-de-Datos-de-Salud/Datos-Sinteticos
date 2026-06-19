"use client";

import Link from "next/link";
import { useMemo, useRef } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { PageOutline, type OutlineItem } from "@/components/layout/page-outline";
import {
  InstructionsPanel,
  type InstructionsEntry,
} from "@/components/layout/instructions-panel";
import { stepHref, PIPELINE_STEPS } from "@/lib/pipeline-steps";
import { useBannerHeight } from "@/lib/use-banner-height";
import { cn } from "@/lib/utils";

export function WizardShell({
  currentSlug,
  canAdvance = true,
  outline = [],
  instructions,
  instructionsOpen,
  instructionsSections,
  onInstructionsToggleSection,
  onInstructionsClose,
  onInstructionsMeasure,
  instructionsBannerHeight,
  children,
}: {
  currentSlug: string;
  canAdvance?: boolean;
  outline?: readonly OutlineItem[];
  /** When provided, renders a collapsible instructions manual on the right. */
  instructions?: readonly InstructionsEntry[];
  /** Controlled open state for the instructions panel. */
  instructionsOpen?: boolean;
  /** Open/collapsed state per section id, shared with the page sections. */
  instructionsSections?: Record<string, boolean>;
  /** Toggles a section — collapses/expands page section and help together. */
  onInstructionsToggleSection?: (id: string) => void;
  /** Closes the instructions panel (close button rendered over the panel). */
  onInstructionsClose?: () => void;
  /** Reports each entry's natural help-block height so the host page can pad
      its sections to fit. Keyed by entry id. */
  onInstructionsMeasure?: (heights: Record<string, number>) => void;
  /** Page banner height — the panel's sticky overview matches it. */
  instructionsBannerHeight?: number;
  children: React.ReactNode;
}) {
  const steps = PIPELINE_STEPS;
  const index = steps.findIndex((s) => s.slug === currentSlug);
  const prev = index > 0 ? steps[index - 1] : null;
  const next = index >= 0 && index < steps.length - 1 ? steps[index + 1] : null;
  const outlineKey = useMemo(() => outline.map((item) => item.id).join("|"), [outline]);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const contentRef = useRef<HTMLDivElement | null>(null);
  const hasInstructions = !!instructions && instructions.length > 0;
  const open = !!instructionsOpen;
  // The page's WizardBanner publishes its real rendered height here; the rail's
  // "Resumen" block is sized to it so the two banners are always the same
  // height. Falls back to the explicit prop if a page sets one.
  const measuredBannerHeight = useBannerHeight();
  const bannerHeight = measuredBannerHeight || instructionsBannerHeight;

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-1 overflow-hidden">
        <PageOutline key={outlineKey} items={outline} scrollRef={scrollRef} />
        {/* The scroll container holds the content column and, when open, the
            instructions column side by side, so the panel scrolls with the
            page and can be measured against the content. */}
        <div ref={scrollRef} className="relative min-w-0 flex-1 overflow-auto">
          <div className="flex min-h-full items-start">
            <div
              ref={contentRef}
              className={cn(
                "min-w-0 py-6 pl-8 pr-8 transition-[flex-basis] duration-300 ease-in-out",
                hasInstructions && open ? "basis-3/5" : "flex-1 basis-full",
              )}
            >
              {children}
            </div>
            {hasInstructions && open && (
              <InstructionsPanel
                entries={instructions}
                contentRef={contentRef}
                openSections={instructionsSections ?? {}}
                onToggleSection={onInstructionsToggleSection ?? (() => {})}
                onClose={onInstructionsClose}
                bannerHeight={bannerHeight}
                onMeasure={onInstructionsMeasure}
              />
            )}
          </div>
        </div>
      </div>

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
          {steps.map((s, i) => (
            <span
              key={s.slug}
              className={cn(
                "h-1.5 rounded-full transition-all",
                i === index ? "w-6 bg-primary" : "w-1.5 bg-muted-foreground/40",
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
