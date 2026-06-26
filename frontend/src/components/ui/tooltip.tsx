"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Info } from "lucide-react";

interface TooltipProps {
  content: string;
  children?: React.ReactNode;
  side?: "top" | "right" | "bottom" | "left";
  className?: string;
  /** Render the trigger wrapper as a <span> instead of a <div>, so the tooltip
   *  can be placed inside phrasing content (<p>, <h4>, …) without producing an
   *  invalid-nesting hydration error. Only safe when children are inline. */
  inline?: boolean;
}

const TOOLTIP_WIDTH = 350;
const GAP = 8;

export function Tooltip({
  content,
  children,
  side = "top",
  className = "",
  inline = false,
}: TooltipProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [coords, setCoords] = useState<{ top: number; left: number } | null>(null);
  // Use HTMLElement so the ref works for both <button> and <div> triggers.
  const triggerRef = useRef<HTMLElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!isOpen || !triggerRef.current) return;

    const updatePosition = () => {
      const trigger = triggerRef.current;
      const tooltip = tooltipRef.current;
      if (!trigger) return;

      const rect = trigger.getBoundingClientRect();
      const tipHeight = tooltip?.offsetHeight ?? 80;
      const tipWidth = tooltip?.offsetWidth ?? TOOLTIP_WIDTH;

      let top = 0;
      let left = 0;

      switch (side) {
        case "top":
          top = rect.top - tipHeight - GAP;
          left = rect.left + rect.width / 2 - tipWidth / 2;
          break;
        case "bottom":
          top = rect.bottom + GAP;
          left = rect.left + rect.width / 2 - tipWidth / 2;
          break;
        case "left":
          top = rect.top + rect.height / 2 - tipHeight / 2;
          left = rect.left - tipWidth - GAP;
          break;
        case "right":
          top = rect.top + rect.height / 2 - tipHeight / 2;
          left = rect.right + GAP;
          break;
      }

      const margin = 8;
      const maxLeft = window.innerWidth - tipWidth - margin;
      const maxTop = window.innerHeight - tipHeight - margin;
      left = Math.min(Math.max(margin, left), maxLeft);
      top = Math.min(Math.max(margin, top), maxTop);

      setCoords({ top, left });
    };

    updatePosition();
    requestAnimationFrame(updatePosition);

    window.addEventListener("scroll", updatePosition, true);
    window.addEventListener("resize", updatePosition);
    return () => {
      window.removeEventListener("scroll", updatePosition, true);
      window.removeEventListener("resize", updatePosition);
    };
  }, [isOpen, side]);

  const hoverProps = {
    onMouseEnter: () => setIsOpen(true),
    onMouseLeave: () => setIsOpen(false),
    onFocus: () => setIsOpen(true),
    onBlur: () => setIsOpen(false),
  };

  const portal = mounted && isOpen && coords
    ? createPortal(
      <div
        ref={tooltipRef}
        role="tooltip"
        onMouseEnter={() => setIsOpen(true)}
        onMouseLeave={() => setIsOpen(false)}
        className="fixed z-[9999] rounded-md border bg-popover px-4 py-3 text-sm text-popover-foreground shadow-md whitespace-normal break-words pointer-events-auto"
        style={{ top: coords.top, left: coords.left, width: TOOLTIP_WIDTH }}
      >
        {content}
      </div>,
      document.body,
    )
    : null;

  if (children) {
    // When `inline`, the wrapper is a <span> so the trigger is valid inside
    // phrasing content (<p>, <h4>, …); otherwise a <div> as before.
    if (inline) {
      return (
        <span
          ref={triggerRef as React.RefObject<HTMLSpanElement>}
          className={`inline-block ${className}`}
          {...hoverProps}
        >
          {children}
          {portal}
        </span>
      );
    }
    return (
      <div
        ref={triggerRef as React.RefObject<HTMLDivElement>}
        className={`inline-block ${className}`}
        {...hoverProps}
      >
        {children}
        {portal}
      </div>
    );
  }

  // When `inline`, the default info trigger is a <span> (role=button) instead
  // of a <button>, so it's valid phrasing content and can live inside another
  // interactive element (e.g. AdvancedSection's collapsible header button)
  // without producing an invalid-nesting hydration error.
  if (inline) {
    return (
      <span className={`relative inline-block ${className}`}>
        <span
          ref={triggerRef as React.RefObject<HTMLSpanElement>}
          role="button"
          tabIndex={0}
          aria-label="Más información"
          {...hoverProps}
          onClick={() => setIsOpen((v) => !v)}
          className="inline-flex items-center justify-center rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
        >
          <Info className="h-4 w-4" />
        </span>
        {portal}
      </span>
    );
  }

  return (
    <div className={`relative inline-block ${className}`}>
      <button
        ref={triggerRef as React.RefObject<HTMLButtonElement>}
        type="button"
        aria-label="Más información"
        {...hoverProps}
        onClick={() => setIsOpen((v) => !v)}
        className="inline-flex items-center justify-center rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
      >
        <Info className="h-4 w-4" />
      </button>
      {portal}
    </div>
  );
}
