"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Info } from "lucide-react";

interface TooltipProps {
  content: string;
  children?: React.ReactNode;
  side?: "top" | "right" | "bottom" | "left";
  className?: string;
}

const TOOLTIP_WIDTH = 350;
const GAP = 8;

export function Tooltip({
  content,
  children,
  side = "top",
  className = "",
}: TooltipProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [coords, setCoords] = useState<{ top: number; left: number } | null>(
    null,
  );
  const triggerRef = useRef<HTMLButtonElement>(null);
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

  return (
    <div className={`relative inline-block ${className}`}>
      <button
        ref={triggerRef}
        type="button"
        onMouseEnter={() => setIsOpen(true)}
        onMouseLeave={() => setIsOpen(false)}
        onFocus={() => setIsOpen(true)}
        onBlur={() => setIsOpen(false)}
        onClick={() => setIsOpen((v) => !v)}
        className="inline-flex items-center justify-center rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
        aria-label="Más información"
      >
        {children || <Info className="h-4 w-4" />}
      </button>

      {mounted && isOpen && coords &&
        createPortal(
          <div
            ref={tooltipRef}
            role="tooltip"
            onMouseEnter={() => setIsOpen(true)}
            onMouseLeave={() => setIsOpen(false)}
            className="fixed z-[9999] rounded-md border bg-popover px-4 py-3 text-sm text-popover-foreground shadow-md whitespace-normal break-words pointer-events-auto"
            style={{
              top: coords.top,
              left: coords.left,
              width: TOOLTIP_WIDTH,
            }}
          >
            {content}
          </div>,
          document.body,
        )}
    </div>
  );
}
