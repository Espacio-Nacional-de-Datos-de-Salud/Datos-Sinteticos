"use client";

import { useCallback, useLayoutEffect, useRef, useState } from "react";
import { ChevronDown, ChevronRight, X } from "lucide-react";

// One help entry. For section entries, `id` must match the DOM id of the page
// section (WorkflowGroup) it documents, so the panel can align to it.
// Overview entries are not tied to a section: they are pinned at the top of
// the panel and are not collapsible.
export type InstructionsEntry = {
  id: string;
  title: string;
  /** Rich help content: prose, option lists, examples, diagrams. */
  content: React.ReactNode;
  /** When true, this entry is pinned at the top and not section-bound. */
  overview?: boolean;
};

// Instructions manual rendered as a right-hand column inside the scrollable
// page. Each help block is absolutely positioned to start level with the page
// section it documents and is collapsible in sync with that section. The host
// page owns the open/closed state map so the two stay synchronised.
export function InstructionsPanel({
  entries,
  contentRef,
  openSections,
  onToggleSection,
  onClose,
  bannerHeight,
  onMeasure,
}: {
  entries: readonly InstructionsEntry[];
  /** The content column — measurement origin. */
  contentRef: React.RefObject<HTMLDivElement | null>;
  /** Open/collapsed state per section id (shared with the page sections). */
  openSections: Record<string, boolean>;
  /** Toggles a section — collapses/expands both page section and help. */
  onToggleSection: (id: string) => void;
  /** Closes the whole instructions panel. */
  onClose?: () => void;
  /** Page banner height — the sticky overview block matches it. */
  bannerHeight?: number;
  /** Reports each entry's natural help-block height, keyed by id. */
  onMeasure?: (heights: Record<string, number>) => void;
}) {
  // Top offset of each documented section, relative to the section layer.
  const [tops, setTops] = useState<Record<string, number>>({});
  // Natural height of each rendered help block.
  const [heights, setHeights] = useState<Record<string, number>>({});
  // Space the page should reserve per id (overview height / section deficit).
  const [reserve, setReserve] = useState<Record<string, number>>({});
  const blockRefs = useRef<Record<string, HTMLElement | null>>({});
  // The absolutely-positioned layer holding the section help blocks.
  const layerRef = useRef<HTMLDivElement | null>(null);

  const measure = useCallback(() => {
    const content = contentRef.current;
    const layer = layerRef.current;
    if (!content || !layer) return;
    // Section help blocks are positioned relative to the section layer; the
    // page reserves a top spacer matching the sticky overview, so the layer's
    // top aligns with the first page section.
    const base = layer.getBoundingClientRect().top;

    const nextTops: Record<string, number> = {};
    for (const entry of entries) {
      const el = document.getElementById(entry.id);
      // Round to whole pixels: sub-pixel jitter between measurements would
      // make shallowEqual always report a change and loop forever.
      if (el) nextTops[entry.id] = Math.round(el.getBoundingClientRect().top - base);
    }

    const nextHeights: Record<string, number> = {};
    // What the page should reserve, keyed by id:
    //  - overview → the sticky block's height (page top spacer).
    //  - section  → the deficit (help height − section height), so the page
    //    can add that much *background* space below the section box.
    const nextReserve: Record<string, number> = {};
    for (const entry of entries) {
      const block = blockRefs.current[entry.id];
      if (!block) continue;
      if (entry.overview) {
        nextHeights[entry.id] = block.scrollHeight;
        nextReserve[entry.id] = block.scrollHeight;
        continue;
      }
      const el = document.getElementById(entry.id);
      if (el && nextTops[entry.id] != null) {
        nextHeights[entry.id] = block.scrollHeight;
        const deficit = block.scrollHeight - el.getBoundingClientRect().height;
        nextReserve[entry.id] = Math.max(0, Math.round(deficit));
      }
    }

    setTops((prev) => (shallowEqual(prev, nextTops) ? prev : nextTops));
    setHeights((prev) => (shallowEqual(prev, nextHeights) ? prev : nextHeights));
    setReserve((prev) => (shallowEqual(prev, nextReserve) ? prev : nextReserve));
  }, [entries, contentRef]);

  useLayoutEffect(() => {
    measure();
    const content = contentRef.current;
    if (!content) return;
    const ro = new ResizeObserver(measure);
    ro.observe(content);
    for (const entry of entries) {
      const el = document.getElementById(entry.id);
      if (el) ro.observe(el);
      const block = blockRefs.current[entry.id];
      if (block) ro.observe(block);
    }
    window.addEventListener("resize", measure);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [entries, contentRef, measure, openSections]);

  // Report the space the page should reserve (overview spacer + per-section
  // background gap when the help is taller than its section).
  useLayoutEffect(() => {
    onMeasure?.(reserve);
  }, [reserve, onMeasure]);

  const columnHeight = entries.reduce((max, e) => {
    if (e.overview) return max;
    const h = heights[e.id];
    const top = tops[e.id];
    return h != null && top != null ? Math.max(max, top + h) : max;
  }, 0);

  return (
    <aside className="relative shrink-0 basis-2/5 border-l border-[#e3e9f4] bg-white dark:border-[#23335b] dark:bg-[#0c1730]">
      {/* Overview blocks — sticky at the top, sized to match the page banner
          so the two banners are the same height. */}
      {entries
        .filter((e) => e.overview)
        .map((entry) => (
          <article
            key={entry.id}
            ref={(el) => {
              blockRefs.current[entry.id] = el;
            }}
            className="sticky top-0 z-20 flex flex-col justify-center gap-1 overflow-hidden border-b border-[#e3e9f4] bg-white px-4 dark:border-[#23335b] dark:bg-[#0c1730]"
            style={bannerHeight ? { height: bannerHeight } : undefined}
          >
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <span className="h-4 w-1.5 rounded-full bg-[#FFDB00]" />
                <span className="text-[14px] font-bold tracking-tight text-[#16386f] dark:text-[#dce8ff]">
                  {entry.title}
                </span>
              </div>
              {onClose && (
                <button
                  type="button"
                  onClick={onClose}
                  aria-label="Cerrar manual de instrucciones"
                  className="flex items-center gap-1.5 rounded-md bg-[#00215C] px-2.5 py-1.5 text-xs font-semibold text-white shadow-sm transition-colors hover:bg-[#04214d]"
                >
                  <X className="h-4 w-4" />
                  Cerrar
                </button>
              )}
            </div>
            <div className="mt-1.5 text-[12.5px] leading-relaxed text-[#3a4a63] dark:text-[#aebdd9]">
              {entry.content}
            </div>
          </article>
        ))}

      {/* Section help blocks — absolutely positioned to align with their page
          section. The layer's top aligns with the first page section because
          the page reserves a spacer matching the sticky overview height. */}
      <div ref={layerRef} className="relative" style={{ height: columnHeight || undefined }}>
        {entries
          .filter((e) => !e.overview)
          .map((entry) => {
            const top = tops[entry.id];
            if (top == null) return null;
            const open = openSections[entry.id] ?? true;
            return (
              <article
                key={entry.id}
                ref={(el) => {
                  blockRefs.current[entry.id] = el;
                }}
                className="absolute left-0 right-0 px-4 py-3"
                style={{ top }}
              >
                {/* Thin rule above the title marks where a section starts. */}
                <div className="mb-2 h-px w-full bg-[#16386f]/20 dark:bg-[#5f83be]/30" />
                <button
                  type="button"
                  onClick={() => onToggleSection(entry.id)}
                  aria-expanded={open}
                  className="flex w-full items-center justify-between gap-3 rounded-md px-1 py-1 text-left transition-colors"
                >
                  <span className="flex items-center gap-2">
                    <span className="h-5 w-1.5 rounded-full bg-[#FFDB00]" />
                    <span className="text-[15px] font-bold tracking-tight text-[#16386f] dark:text-[#dce8ff]">
                      {entry.title}
                    </span>
                  </span>
                  {open ? (
                    <ChevronDown className="h-4 w-4 shrink-0 text-[#5f83be]" />
                  ) : (
                    <ChevronRight className="h-4 w-4 shrink-0 text-[#5f83be]" />
                  )}
                </button>

                {open && (
                  <div className="mt-2 space-y-2.5 pl-3.5 text-[12.5px] leading-relaxed text-[#3a4a63] dark:text-[#aebdd9]">
                    {entry.content}
                  </div>
                )}
              </article>
            );
          })}
      </div>
    </aside>
  );
}

function shallowEqual(a: Record<string, number>, b: Record<string, number>) {
  const ka = Object.keys(a);
  const kb = Object.keys(b);
  if (ka.length !== kb.length) return false;
  return ka.every((k) => a[k] === b[k]);
}
