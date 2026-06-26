// Uniform "advanced / optional" treatment.
//
// Since the app dropped the básico/avanzado mode split, every feature lives in
// one UI. Features that used to be advanced-only now render through this
// component so they share one visual language: a Sparkles (✦) marker in the
// app accent color, an accent-tinted left border + muted background, an info
// tooltip explaining they're optional, and — for `AdvancedSection` — a
// collapsed-by-default body that the user must open explicitly.

"use client";

import * as React from "react";
import { ChevronDown, ChevronRight, Sparkles } from "lucide-react";

import { cn } from "@/lib/utils";
import { Tooltip } from "@/components/ui/tooltip";

const ADVANCED_HINT = "Opcional · ajuste avanzado";

// Shared soft pastel-lavender tint so every advanced surface (sections, cards,
// badges) reads as the same "optional / advanced" thing — a faint wash that's
// clearly not a neutral card, without shouting.
const ADVANCED_CARD_CLASS =
  "border-violet-200/60 bg-violet-50/30 dark:border-violet-900/40 dark:bg-violet-950/10";

type AdvancedSectionProps = React.ComponentProps<"section"> & {
  title: string;
  /** Optional sub-label rendered next to the title in muted text. */
  hint?: string;
  /** Tooltip on the info icon — adapt it to the section, not always generic. */
  tooltip?: string;
  /** Advanced sections start collapsed; the user opens them explicitly. */
  defaultOpen?: boolean;
  /** Controlled open state. When provided, `onOpenChange` must update it. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
};

function AdvancedSection({
  title,
  hint,
  tooltip = ADVANCED_HINT,
  className,
  children,
  defaultOpen = false,
  open: openProp,
  onOpenChange,
  ...props
}: AdvancedSectionProps) {
  const [uncontrolledOpen, setUncontrolledOpen] = React.useState(defaultOpen);
  const isControlled = openProp !== undefined;
  const open = isControlled ? openProp : uncontrolledOpen;
  const contentId = React.useId();
  const sectionRef = React.useRef<HTMLElement | null>(null);

  const handleToggle = () => {
    const next = !open;
    if (next) {
      requestAnimationFrame(() => {
        sectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }
    if (isControlled) onOpenChange?.(next);
    else setUncontrolledOpen(next);
  };

  return (
    <section
      ref={sectionRef}
      className={cn(
        "relative rounded-lg border p-3 pl-4 shadow-sm",
        ADVANCED_CARD_CLASS,
        "before:absolute before:inset-y-3 before:left-0 before:w-1 before:rounded-r-full before:bg-violet-300/70 dark:before:bg-violet-500/50",
        className,
      )}
      {...props}
    >
      <button
        type="button"
        className="flex w-full items-center justify-between gap-3 rounded-md px-1 py-1 text-left transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-expanded={open}
        aria-controls={contentId}
        onClick={handleToggle}
      >
        <span className="flex items-center gap-2 text-sm font-medium">
          <Sparkles className="h-3.5 w-3.5 shrink-0 text-violet-400 dark:text-violet-300" aria-hidden />
          <span>{title}</span>
          {hint ? (
            <span className="text-xs font-normal text-muted-foreground">{hint}</span>
          ) : null}
        </span>
        <span className="flex items-center gap-1.5">
          <span onClick={(e) => e.stopPropagation()} className="flex items-center">
            <Tooltip content={tooltip} side="left" inline />
          </span>
          {open ? (
            <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
          )}
        </span>
      </button>

      {open ? (
        <div id={contentId} className="space-y-4 pt-3">
          {children}
        </div>
      ) : null}
    </section>
  );
}

/** Inline marker for advanced/optional bits that aren't full collapsible
 *  sections (a note, a heading, a single informational field). Icon-only ✦ chip
 *  whose meaning lives in the hover tooltip — no visible label. Pass `tooltip`
 *  to adapt the hint to the spot (it isn't always "optional/advanced" — it may
 *  be plain info, or flag a whole advanced section). */
function AdvancedBadge({
  tooltip = ADVANCED_HINT,
  className,
}: {
  tooltip?: string;
  className?: string;
}) {
  return (
    <Tooltip content={tooltip} side="top" className={className} inline>
      <span
        className="inline-flex items-center justify-center rounded-full border border-violet-200/70 bg-violet-50/60 p-1 text-violet-500 dark:border-violet-300 dark:bg-violet-500 dark:text-white"
        aria-label={tooltip}
      >
        <Sparkles className="h-3 w-3" aria-hidden />
      </span>
    </Tooltip>
  );
}

export { AdvancedSection, AdvancedBadge, ADVANCED_HINT, ADVANCED_CARD_CLASS };
