"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronRight, ChevronsUpDown, ListTree } from "lucide-react";

import { cn } from "@/lib/utils";

export type OutlineItem = {
  id: string;
  label: string;
  level?: 1 | 2;
};

export function PageOutline({
  items,
  scrollRef,
}: {
  items: readonly OutlineItem[];
  scrollRef?: React.RefObject<HTMLDivElement | null>;
}) {
  const [activeId, setActiveId] = useState(items[0]?.id ?? "");
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>(() => {
    const initialState: Record<string, boolean> = {};
    items.forEach((item) => {
      const level = item.level ?? 1;
      if (level === 1) {
        initialState[item.id] = true;
      }
    });
    return initialState;
  });
  // While a click-driven scroll is animating, ignore scroll events so they
  // don't override the section the user explicitly navigated to.
  const lockUntilRef = useRef(0);

  useEffect(() => {
    if (items.length === 0) return;

    const container = scrollRef?.current;
    if (!container) return;

    const updateActive = () => {
      if (Date.now() < lockUntilRef.current) return;

      // When scrolled to the bottom, the last section can't reach the
      // threshold, so highlight it explicitly.
      if (container.scrollTop + container.clientHeight >= container.scrollHeight - 2) {
        setActiveId(items[items.length - 1]?.id ?? "");
        return;
      }

      // A section becomes "active" once its top edge has scrolled past
      // 120 px below the container's visible top edge.
      const threshold = container.getBoundingClientRect().top + 120;
      let next = items[0]?.id ?? "";
      for (const item of items) {
        const el = document.getElementById(item.id);
        if (el && el.getBoundingClientRect().top <= threshold) {
          next = item.id;
        }
      }
      setActiveId(next);
    };

    updateActive();
    container.addEventListener("scroll", updateActive, { passive: true });
    return () => container.removeEventListener("scroll", updateActive);
  }, [items, scrollRef]);

  const scrollToId = (id: string, parentId?: string) => {
    const target = document.getElementById(id);
    if (target) {
      // Open any collapsed WorkflowGroup ancestors before scrolling.
      let current: HTMLElement | null = target.parentElement;
      while (current) {
        const btn = current.querySelector<HTMLButtonElement>("button[aria-expanded]");
        if (btn && btn.getAttribute("aria-expanded") === "false") btn.click();
        current = current.parentElement;
      }
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    } else if (parentId) {
      // Child element is not in the DOM because its parent group is collapsed.
      // Open the parent first, then scroll once it renders.
      const parentSection = document.getElementById(parentId);
      const btn = parentSection?.querySelector<HTMLButtonElement>("button[aria-expanded]");
      if (btn && btn.getAttribute("aria-expanded") === "false") btn.click();
      requestAnimationFrame(() =>
        requestAnimationFrame(() => {
          document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
        }),
      );
    }
  };

  const handleItemClick = (item: OutlineItem, parentId?: string) => {
    if (item.level === 1) {
      setExpandedGroups((prev) => ({
        ...prev,
        [item.id]: !prev[item.id],
      }));
    } else if (parentId && item.level === 2) {
      setExpandedGroups((prev) => ({
        ...prev,
        [parentId]: true,
      }));
    }

    // Immediately reflect the click in the sidebar, and lock out scroll
    // tracking until the smooth scroll finishes so it isn't overridden.
    setActiveId(item.id);
    lockUntilRef.current = Date.now() + 800;
    scrollToId(item.id, parentId);
  };

  if (items.length === 0) return null;

  const groupedItems = items.reduce<Array<{ parent: OutlineItem; children: OutlineItem[] }>>(
    (acc, item) => {
      const level = item.level ?? 1;
      if (level === 1) {
        acc.push({ parent: item, children: [] });
      } else if (acc.length > 0) {
        acc[acc.length - 1].children.push(item);
      }
      return acc;
    },
    [],
  );

  return (
    <aside className="hidden h-full w-64 shrink-0 overflow-hidden border-r border-[#c9d4ea] bg-[#eef3ff] text-[#2b3a52] xl:flex xl:flex-col dark:border-[#2a3960] dark:bg-[#0f1d39] dark:text-[#c5d2ea]">
      <div className="flex h-14 items-center gap-2 border-b border-[#d8e2f4] bg-[#e4ecfb] px-4 text-[11px] font-bold uppercase tracking-[0.08em] text-[#26467a] dark:border-[#33456f] dark:bg-[#132546] dark:text-[#9db4dc]">
        <ListTree className="h-3.5 w-3.5 shrink-0" />
        <span className="flex-1 truncate">En esta pagina</span>
        <button
          type="button"
          title="Contraer todo"
          onClick={() => {
            const container = scrollRef?.current;
            if (!container) return;
            container
              .querySelectorAll<HTMLButtonElement>(
                "button[data-workflow-group-toggle][aria-expanded='true']",
              )
              .forEach((btn) => btn.click());
          }}
          className="shrink-0 rounded p-0.5 opacity-60 transition-opacity hover:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#5f83be]"
        >
          <ChevronsUpDown className="h-3.5 w-3.5" />
        </button>
      </div>
      <nav className="flex-1 overflow-y-auto py-2">
        {groupedItems.map(({ parent, children }) => {
          const isParentActive = parent.id === activeId;
          const isExpanded = expandedGroups[parent.id] ?? true;

          return (
            <div key={parent.id}>
              <button
                type="button"
                onClick={() => handleItemClick(parent)}
                className={cn(
                  "flex w-full items-center gap-1 border-l-[3px] px-4 py-2 text-left text-[13px] font-semibold transition-colors",
                  isParentActive
                    ? "border-l-[#5f83be] bg-white text-[#16386f] dark:border-l-[#7ea1d8] dark:bg-[#1a2e57] dark:text-[#dce8ff]"
                    : "border-l-transparent text-[#334868] hover:bg-white/80 dark:text-[#9fb4d9] dark:hover:bg-[#17294e]",
                )}
              >
                <span className="shrink-0">
                  {isExpanded ? (
                    <ChevronDown className="h-4 w-4" />
                  ) : (
                    <ChevronRight className="h-4 w-4" />
                  )}
                </span>
                <span className="flex-1 truncate">{parent.label}</span>
              </button>
              {isExpanded && children.length > 0 && (
                <div>
                  {children.map((child) => {
                    const isChildActive = child.id === activeId;
                    return (
                      <button
                        key={child.id}
                        type="button"
                        onClick={() => handleItemClick(child, parent.id)}
                        className={cn(
                          "flex w-full items-center border-l-[3px] px-4 py-2 pl-12 text-left text-[13px] transition-colors",
                          "text-[#52698f] dark:text-[#8ea5cf]",
                          isChildActive
                            ? "border-l-[#5f83be] bg-white text-[#16386f] dark:border-l-[#7ea1d8] dark:bg-[#1a2e57] dark:text-[#dce8ff]"
                            : "border-l-transparent hover:bg-white/80 dark:hover:bg-[#17294e]",
                        )}
                      >
                        <span className="truncate">{child.label}</span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </nav>
    </aside>
  );
}
