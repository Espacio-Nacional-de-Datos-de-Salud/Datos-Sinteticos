// Uniform expand/collapse button used across step cards.
//
// All collapsible sections (config panels, history tables, profiling, etc.)
// render the same chevron + Mostrar/Ocultar label on the right side of the
// card header so the toggle lands in a predictable place.

"use client";

import { ChevronDown, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";

type Props = {
  open: boolean;
  onToggle: () => void;
  showLabel?: string;
  hideLabel?: string;
  ariaLabel?: string;
};

export function CollapseToggle({
  open,
  onToggle,
  showLabel = "Mostrar",
  hideLabel = "Ocultar",
  ariaLabel,
}: Props) {
  const handleClick = (event: React.MouseEvent<HTMLButtonElement>) => {
    const willOpen = !open;
    // Capture the card before the toggle re-renders the subtree.
    const card = event.currentTarget.closest<HTMLElement>('[data-slot="card"]');
    onToggle();
    if (willOpen && card) {
      // Match the breathing room used by the page's larger sections.
      card.style.scrollMarginTop = "6rem";
      // Wait for the expanded content to render before scrolling.
      requestAnimationFrame(() =>
        requestAnimationFrame(() => {
          card.scrollIntoView({ behavior: "smooth", block: "start" });
        }),
      );
    }
  };

  return (
    <Button
      type="button"
      size="sm"
      variant="outline"
      aria-expanded={open}
      aria-label={ariaLabel}
      onClick={handleClick}
    >
      {open ? (
        <ChevronDown className="h-4 w-4" />
      ) : (
        <ChevronRight className="h-4 w-4" />
      )}
      <span className="ml-1 text-xs">{open ? hideLabel : showLabel}</span>
    </Button>
  );
}
