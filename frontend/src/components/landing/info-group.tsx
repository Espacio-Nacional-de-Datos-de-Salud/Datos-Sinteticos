"use client";

import { useState } from "react";
import type { LucideIcon } from "lucide-react";
import { ChevronDown, ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";

export type InfoSubsection = {
  id: string;
  title: string;
  summary: string;
  content: React.ReactNode;
  Icon: LucideIcon;
};

// Renders the descriptive landing sections as a compact accordion. All items
// start collapsed so the group stays small; the user expands only what they
// want to read.
export function InfoGroup({ sections }: { sections: readonly InfoSubsection[] }) {
  const [openId, setOpenId] = useState<string | null>(null);

  return (
    <div className="space-y-2">
      {sections.map((sub) => {
        const Icon = sub.Icon;
        const isOpen = openId === sub.id;
        return (
          <div
            key={sub.id}
            id={sub.id}
            className="scroll-mt-28 overflow-hidden rounded-xl border border-[#d8e3f4] bg-white dark:border-border dark:bg-card"
          >
            <button
              type="button"
              aria-expanded={isOpen}
              onClick={() => setOpenId((prev) => (prev === sub.id ? null : sub.id))}
              className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
            >
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#eef3ff] text-[#114da6] dark:bg-accent dark:text-[#FFDB00]">
                  <Icon className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <h3 className="text-sm font-semibold text-[#00215C] dark:text-white">
                    {sub.title}
                  </h3>
                  {!isOpen && (
                    <p className="mt-0.5 line-clamp-1 text-xs text-slate-500 dark:text-muted-foreground">
                      {sub.summary}
                    </p>
                  )}
                </div>
              </div>
              {isOpen ? (
                <ChevronDown className="h-4 w-4 shrink-0 text-[#114da6] dark:text-[#FFDB00]" />
              ) : (
                <ChevronRight className="h-4 w-4 shrink-0 text-[#114da6] dark:text-[#FFDB00]" />
              )}
            </button>
            {isOpen && (
              <div
                className={cn(
                  "border-t border-[#eef0f6] px-4 py-4 text-sm leading-7 text-slate-700",
                  "dark:border-border dark:text-muted-foreground",
                )}
              >
                {sub.content}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
