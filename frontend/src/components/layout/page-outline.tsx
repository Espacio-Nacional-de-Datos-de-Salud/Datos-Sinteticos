"use client";

import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight, ListTree } from "lucide-react";

import { cn } from "@/lib/utils";

export type OutlineItem = {
  id: string;
  label: string;
  level?: 1 | 2;
};

export function PageOutline({ items }: { items: readonly OutlineItem[] }) {
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

  useEffect(() => {
    if (items.length === 0) return;

    const elements = items
      .map((item) => document.getElementById(item.id))
      .filter((element): element is HTMLElement => Boolean(element));

    if (elements.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible.length > 0) {
          setActiveId(visible[0].target.id);
        }
      },
      {
        rootMargin: "-18% 0px -62% 0px",
        threshold: [0, 0.2, 0.5, 1],
      },
    );

    elements.forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, [items]);

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

    const target = document.getElementById(item.id);
    if (target) {
      // Find and expand any parent WorkflowGroup sections
      let current = target.parentElement;
      while (current) {
        // Look for WorkflowGroup containers (sections with toggle buttons)
        const toggleButton = current.querySelector('button[aria-expanded]');
        if (toggleButton && toggleButton.getAttribute('aria-expanded') === 'false') {
          // Click the button to expand
          (toggleButton as HTMLButtonElement).click();
        }
        current = current.parentElement;
      }

      target.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }
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
    []
  );

  return (
    <aside className="hidden min-h-full w-64 shrink-0 self-stretch overflow-hidden border-r border-[#c9d4ea] bg-[#eef3ff] text-[#2b3a52] xl:flex xl:flex-col">
      <div className="flex h-14 items-center gap-2 border-b border-[#d8e2f4] bg-[#e4ecfb] px-4 text-[11px] font-bold uppercase tracking-[0.08em] text-[#26467a]">
        <ListTree className="h-3.5 w-3.5" />
        En esta pagina
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
                    ? "border-l-[#5f83be] bg-white text-[#16386f]"
                    : "border-l-transparent text-[#334868] hover:bg-white/80",
                )}
              >
                <span className="shrink-0">
                  {isExpanded ? (
                    <ChevronDown className="h-4 w-4" />
                  ) : (
                    <ChevronRight className="h-4 w-4" />
                  )}
                </span>
                <span className="truncate flex-1">{parent.label}</span>
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
                          "text-[#52698f]",
                          isChildActive
                            ? "border-l-[#5f83be] bg-white text-[#16386f]"
                            : "border-l-transparent hover:bg-white/80",
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
