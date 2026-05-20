"use client";

import { useEffect, useState } from "react";
import { ListTree } from "lucide-react";

import { cn } from "@/lib/utils";

export type OutlineItem = {
  id: string;
  label: string;
  level?: 1 | 2;
};

export function PageOutline({ items }: { items: OutlineItem[] }) {
  const [activeId, setActiveId] = useState(items[0]?.id ?? "");

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

  if (items.length === 0) return null;

  return (
    <aside className="hidden min-h-full w-64 shrink-0 self-stretch overflow-hidden border-r border-[#c9d4ea] bg-[#eef3ff] text-[#2b3a52] xl:flex xl:flex-col">
      <div className="flex h-14 items-center gap-2 border-b border-[#d8e2f4] bg-[#e4ecfb] px-4 text-[11px] font-bold uppercase tracking-[0.08em] text-[#26467a]">
        <ListTree className="h-3.5 w-3.5" />
        En esta pagina
      </div>
      <nav className="flex-1 overflow-y-auto py-2">
        {items.map((item) => {
          const isActive = item.id === activeId;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => {
                document.getElementById(item.id)?.scrollIntoView({
                  behavior: "smooth",
                  block: "start",
                });
              }}
              className={cn(
                "flex w-full items-center border-l-[3px] px-4 py-2 text-left text-[13px] transition-colors",
                item.level === 2 ? "pl-8 text-[#52698f]" : "font-semibold text-[#334868]",
                isActive
                  ? "border-l-[#5f83be] bg-white text-[#16386f]"
                  : "border-l-transparent hover:bg-white/80",
              )}
            >
              <span className="truncate">{item.label}</span>
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
