"use client";

import { useLayoutEffect, useRef } from "react";
import { BookOpen } from "lucide-react";
import { WIZARD_BANNER_HEIGHT } from "@/components/layout/wizard-banner-height";
import { usePublishBannerHeight } from "@/lib/use-banner-height";

// Re-export so existing `import { WIZARD_BANNER_HEIGHT } from ".../wizard-banner"`
// sites keep working.
export { WIZARD_BANNER_HEIGHT };

// Shared sticky top banner for every pipeline wizard page.
//
// Why this exists: each page used to roll its own banner, so the title, the
// "Manual de instrucciones" button and the banner height all landed in
// slightly different places page to page. That broke the illusion that the
// instructions rail is one panel that follows you: its sticky "Resumen" block
// is sized to the banner, so a different banner height meant the rail's title,
// "Cerrar" button and overview diagram jumped around as you navigated.
//
// This component gives every banner the same MINIMUM height
// (WIZARD_BANNER_HEIGHT) so the title, the manual button and the rail's
// overview diagram line up across all five pages at rest. A page whose status
// content needs more room can still grow taller — all info stays visible, the
// banner just expands downward. The banner publishes its real measured height
// (see use-banner-height) so the rail's "Resumen" block matches it exactly,
// even on a page whose banner grew past the minimum.

export function WizardBanner({
  title,
  titleBadge,
  subtitle,
  info,
  instructionsOpen,
  onOpenManual,
}: {
  /** Page title (e.g. "Entrenamiento"). Always top-left, same spot every page. */
  title: string;
  /** Optional marker rendered next to the title (e.g. an advanced badge). */
  titleBadge?: React.ReactNode;
  /** Short description under the title. Kept to ~2 lines. */
  subtitle?: React.ReactNode;
  /** Variable status/name/selector content (progress panel, name row, dropdown).
      Always fully visible; the banner grows downward if it needs more room. */
  info?: React.ReactNode;
  /** Whether the instructions rail is open — hides the manual button when so. */
  instructionsOpen?: boolean;
  /** Opens the instructions rail. */
  onOpenManual?: () => void;
}) {
  // Publish the banner's real rendered height so the rail's "Resumen" block can
  // match it exactly (the shared min-height keeps pages aligned at rest; this
  // keeps them aligned when a banner grows past the minimum too).
  const rootRef = useRef<HTMLDivElement | null>(null);
  const publishHeight = usePublishBannerHeight();
  useLayoutEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const update = () => publishHeight(el.getBoundingClientRect().height);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [publishHeight]);

  return (
    <div
      ref={rootRef}
      className="sticky top-0 z-20 -mx-8 -mt-6 mb-6 border-b bg-background/95 px-8 py-4 backdrop-blur supports-[backdrop-filter]:bg-background/80"
      style={{ minHeight: WIZARD_BANNER_HEIGHT }}
    >
      {/* Manual button — pinned to the same top-right spot on every page. */}
      {!instructionsOpen && onOpenManual && (
        <button
          type="button"
          onClick={onOpenManual}
          aria-label="Abrir manual de instrucciones"
          className="absolute right-8 top-4 z-10 flex items-center gap-2 rounded-lg bg-[#FFDB00] px-4 py-2.5 text-sm font-bold text-[#00215C] shadow-md transition-colors hover:bg-[#f0cf00]"
        >
          <BookOpen className="h-5 w-5" />
          Manual de instrucciones
        </button>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {titleBadge}
      </div>
      {subtitle && (
        // Reserve room on the right so the subtitle never runs under the
        // manual button.
        <div className="mt-0.5 max-w-[calc(100%-15rem)] text-sm text-muted-foreground">
          {subtitle}
        </div>
      )}
      {info && <div className="mt-2">{info}</div>}
    </div>
  );
}
