"use client";

import { useEffect, useRef, useState } from "react";
import { Download } from "lucide-react";

import { API_BASE_URL } from "@/lib/api";

export type DownloadOption = {
  label: string;
  /** API path (without origin). Joined with API_BASE_URL. */
  href: string;
};

export function DownloadMenu({
  ariaLabel,
  options,
  disabled,
}: {
  ariaLabel: string;
  options: DownloadOption[];
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative inline-block">
      <button
        type="button"
        aria-label={ariaLabel}
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
        className="rounded p-1 text-muted-foreground hover:bg-primary/10 hover:text-primary disabled:opacity-40"
      >
        <Download className="h-3.5 w-3.5" />
      </button>
      {open && (
        <div className="absolute right-0 z-50 mt-1 min-w-[12rem] overflow-hidden rounded-md border bg-popover text-popover-foreground shadow-md">
          {options.map((opt) => (
            <a
              key={opt.label}
              href={`${API_BASE_URL}${opt.href}`}
              download
              onClick={() => setOpen(false)}
              className="block px-3 py-1.5 text-left text-xs hover:bg-accent hover:text-accent-foreground"
            >
              {opt.label}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
