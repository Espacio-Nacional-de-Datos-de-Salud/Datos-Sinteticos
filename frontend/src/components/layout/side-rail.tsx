"use client";

// A sticky right-hand rail the user can collapse to a thin strip and
// drag-resize horizontally. The width is stored as a percentage of the rail's
// flex container so it survives reloads and adapts to the viewport width.
//
// Must be rendered as the last child of a horizontal flex container whose
// other child is the main column with `flex-1 min-w-0` — the rail reads its
// own `parentElement` to convert pointer movement into a width percentage.

import { useCallback, useEffect, useRef, useState } from "react";
import { PanelRightClose, PanelRightOpen } from "lucide-react";

import { usePersistentState } from "@/lib/use-persistent-state";

export function SideRail({
  storageKey,
  top,
  height,
  title = "panel",
  defaultPct = 40,
  minPct = 25,
  maxPct = 65,
  children,
}: {
  /** Base localStorage key; `.collapsed` and `.pct` are derived from it. */
  storageKey: string;
  /** Sticky top offset in px (e.g. the page banner height). */
  top: number;
  /** CSS height for the sticky rail (e.g. visible area below the banner). */
  height: string;
  /** Used in the collapse/expand button labels. */
  title?: string;
  defaultPct?: number;
  minPct?: number;
  maxPct?: number;
  children: React.ReactNode;
}) {
  const [collapsed, setCollapsed] = usePersistentState(`${storageKey}.collapsed`, false);
  const [pct, setPct] = usePersistentState(`${storageKey}.pct`, defaultPct);
  const [dragging, setDragging] = useState(false);
  const asideRef = useRef<HTMLElement | null>(null);
  const draggingRef = useRef(false);

  const onPointerMove = useCallback(
    (e: PointerEvent) => {
      if (!draggingRef.current) return;
      const container = asideRef.current?.parentElement;
      if (!container) return;
      const rect = container.getBoundingClientRect();
      if (rect.width === 0) return;
      const next = ((rect.right - e.clientX) / rect.width) * 100;
      setPct(Math.min(maxPct, Math.max(minPct, Math.round(next))));
    },
    [maxPct, minPct, setPct],
  );

  const stopDragging = useCallback(() => {
    draggingRef.current = false;
    setDragging(false);
  }, []);

  useEffect(() => {
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", stopDragging);
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", stopDragging);
    };
  }, [onPointerMove, stopDragging]);

  const startDragging = (e: React.PointerEvent) => {
    e.preventDefault();
    draggingRef.current = true;
    setDragging(true);
  };

  const stickyStyle = {
    position: "sticky" as const,
    top,
    alignSelf: "flex-start" as const,
    height,
  };

  if (collapsed) {
    return (
      <aside
        ref={asideRef}
        className="flex w-10 shrink-0 flex-col items-center border-l border-[#e3e9f4] bg-background pt-3 dark:border-[#23335b]"
        style={stickyStyle}
      >
        <button
          type="button"
          onClick={() => setCollapsed(false)}
          title={`Mostrar ${title}`}
          aria-label={`Mostrar ${title}`}
          className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <PanelRightOpen className="h-4 w-4" />
        </button>
      </aside>
    );
  }

  return (
    <aside
      ref={asideRef}
      className="relative min-w-0 shrink-0 self-stretch border-l border-[#e3e9f4] bg-background pl-6 dark:border-[#23335b]"
      style={{ ...stickyStyle, width: `${pct}%` }}
    >
      {/* Drag handle straddling the left divider. */}
      <div
        onPointerDown={startDragging}
        role="separator"
        aria-orientation="vertical"
        title="Arrastra para redimensionar"
        className="group absolute -left-1 top-0 z-10 flex h-full w-2 cursor-col-resize items-center justify-center"
      >
        <span className="h-10 w-1 rounded-full bg-border transition-colors group-hover:bg-primary/60" />
      </div>

      <div className="flex h-full flex-col">
        <div className="flex h-7 shrink-0 items-center justify-end">
          <button
            type="button"
            onClick={() => setCollapsed(true)}
            title={`Ocultar ${title}`}
            aria-label={`Ocultar ${title}`}
            className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <PanelRightClose className="h-4 w-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1">{children}</div>
      </div>

      {/* While dragging, an overlay captures the pointer so iframes/selects in
          either column don't swallow the move events. */}
      {dragging && <div className="fixed inset-0 z-50 cursor-col-resize" />}
    </aside>
  );
}
