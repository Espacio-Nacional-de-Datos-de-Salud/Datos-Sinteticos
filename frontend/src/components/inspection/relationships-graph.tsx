// ER diagram for detected relationships.
//
// Renders the autodetect schema (tables, PKs, FKs) as a Mermaid erDiagram so
// the user can see at a glance which tables connect to which. Mermaid is
// loaded lazily on the client because it touches the DOM and bloats the
// initial JS bundle if imported up-front.

"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { Autodetect, ForeignKey } from "@/lib/api";
import { Maximize2, ZoomIn, ZoomOut, RotateCcw, X, Layout } from "lucide-react";
import { Button } from "@/components/ui/button";

// Sanitise a name for use as a Mermaid entity id. Mermaid is picky about
// characters in entity names — we keep [a-zA-Z0-9_], replace the rest with
// underscores, and prefix with `T_` so digit-leading names don't break.
function sanitizeId(name: string): string {
  const safe = name.replace(/[^a-zA-Z0-9_]/g, "_");
  return /^[a-zA-Z]/.test(safe) ? safe : `T_${safe}`;
}

function buildErDiagram(
  encodingTypes: Record<string, Record<string, string>>,
  pks: Record<string, string>,
  fks: ForeignKey[],
  direction?: "TB" | "LR",
): string {
  const lines: string[] = ["erDiagram"];
  if (direction) {
    lines.push(`  direction ${direction}`);
  }
  // Track table -> sanitized id and remember original names for the label.
  const ids = new Map<string, string>();
  for (const t of Object.keys(encodingTypes)) {
    ids.set(t, sanitizeId(t));
  }
  // Make sure tables that only appear in fks/pks but not encoding_types still
  // show up as bare entities so the relationship arrows have endpoints.
  for (const t of [...Object.keys(pks), ...fks.flatMap((f) => [f.parent, f.child])]) {
    if (!ids.has(t)) ids.set(t, sanitizeId(t));
  }

  const fkColumnsByTable = new Map<string, Set<string>>();
  for (const fk of fks) {
    if (!fkColumnsByTable.has(fk.child)) fkColumnsByTable.set(fk.child, new Set());
    fkColumnsByTable.get(fk.child)!.add(fk.fk_column);
  }

  // Only emit PK and FK columns — the full schema is too noisy for an
  // overview diagram. Other columns are visible in the Types card.
  for (const [table, id] of ids) {
    const cols = encodingTypes[table] ?? {};
    const pkCol = pks[table];
    const fkCols = fkColumnsByTable.get(table) ?? new Set<string>();

    lines.push(`  ${id} {`);
    if (pkCol) {
      const safeType = (cols[pkCol] ?? "id").replace(/[^a-zA-Z0-9_]/g, "_") || "id";
      lines.push(`    ${safeType} ${sanitizeId(pkCol)} PK`);
    }
    for (const fkCol of fkCols) {
      if (fkCol === pkCol) continue;
      const safeType = (cols[fkCol] ?? "id").replace(/[^a-zA-Z0-9_]/g, "_") || "id";
      lines.push(`    ${safeType} ${sanitizeId(fkCol)} FK`);
    }
    lines.push(`  }`);
  }

  for (const fk of fks) {
    const parent = ids.get(fk.parent)!;
    const child = ids.get(fk.child)!;
    // One parent has many children (standard FK direction).
    const label = `"${fk.fk_column}${fk.is_context ? " (context)" : ""}"`;
    lines.push(`  ${parent} ||--o{ ${child} : ${label}`);
  }

  return lines.join("\n");
}

export function RelationshipsGraph({
  autodetect,
  direction: initialDirection = "TB",
}: {
  autodetect: Autodetect;
  direction?: "TB" | "LR";
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [svg, setSvg] = useState<string | null>(null);
  const [direction, setDirection] = useState<"TB" | "LR">(initialDirection);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalZoom, setModalZoom] = useState(1.0);
  const [mounted, setMounted] = useState(false);

  // Sync state if prop changes
  useEffect(() => {
    setDirection(initialDirection);
  }, [initialDirection]);

  // Set mounted state for Next.js portals
  useEffect(() => {
    setMounted(true);
  }, []);

  const diagram = useMemo(
    () =>
      buildErDiagram(
        autodetect.encoding_types ?? {},
        autodetect.relationships?.pks ?? {},
        autodetect.relationships?.fks ?? [],
        direction,
      ),
    [autodetect, direction],
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { default: mermaid } = await import("mermaid");
        mermaid.initialize({
          startOnLoad: false,
          theme: "neutral",
          securityLevel: "strict",
          er: { useMaxWidth: true },
        });
        const id = `er-${Math.random().toString(36).slice(2)}`;
        const { svg } = await mermaid.render(id, diagram);
        if (!cancelled) setSvg(svg);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [diagram]);

  const tableCount = Object.keys(autodetect.encoding_types ?? {}).length;
  const fkCount = (autodetect.relationships?.fks ?? []).length;

  if (tableCount === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No hay tablas detectadas para representar.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {error && (
        <p className="text-sm text-destructive">
          No se pudo renderizar el diagrama: {error}
        </p>
      )}
      {svg ? (
        <div className="relative group rounded-md border bg-card p-3 overflow-hidden">
          {/* Main small diagram */}
          <div
            ref={containerRef}
            className="overflow-auto max-h-[350px] [&_svg]:max-w-full [&_svg]:h-auto"
            dangerouslySetInnerHTML={{ __html: svg }}
          />

          {/* Floating actions in the card */}
          <div className="absolute top-2 right-2 flex items-center gap-1.5 rounded-md border bg-background/95 p-1 shadow-sm opacity-90 hover:opacity-100 transition-opacity z-10">
            <Button
              type="button"
              variant="outline"
              size="xs"
              className="text-xs px-2 h-6"
              onClick={() => setDirection((prev) => (prev === "LR" ? "TB" : "LR"))}
            >
              <Layout className="mr-1 h-3 w-3" />
              {direction === "LR" ? "Vertical" : "Horizontal"}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="xs"
              className="text-xs px-2 h-6"
              onClick={() => setIsModalOpen(true)}
            >
              <Maximize2 className="mr-1 h-3 w-3" />
              Ampliar
            </Button>
          </div>
        </div>
      ) : (
        <div className="rounded-md border bg-card p-3">
          {!error && (
            <p className="text-sm text-muted-foreground">Generando diagrama…</p>
          )}
        </div>
      )}
      <p className="text-xs text-muted-foreground">
        {tableCount} tablas · {fkCount} relaciones
      </p>

      {/* Full-screen detail Modal rendered with createPortal to escape nested layout restrictions */}
      {isModalOpen && svg && mounted && createPortal(
        <div
          className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 md:p-8 animate-in fade-in duration-200"
          onClick={() => setIsModalOpen(false)}
        >
          <div
            className="flex h-[90vh] w-[95vw] max-w-7xl flex-col rounded-lg border bg-background shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex flex-wrap items-center justify-between border-b px-6 py-4 bg-muted/20 gap-4">
              <div>
                <h3 className="font-semibold text-lg text-foreground">Modelo de Relaciones</h3>
                <p className="text-xs text-muted-foreground">
                  {tableCount} tablas · {fkCount} relaciones · Ajusta el zoom y la orientación para inspeccionar en detalle
                </p>
              </div>
              
              {/* Controls */}
              <div className="flex items-center flex-wrap gap-2.5">
                {/* Zoom controls */}
                <div className="flex items-center gap-1.5 bg-muted/60 p-1 rounded-md border">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-8 text-xs px-2.5"
                    disabled={modalZoom <= 0.4}
                    onClick={() => setModalZoom((z) => Math.max(0.4, z - 0.15))}
                    title="Alejar"
                  >
                    <ZoomOut className="mr-1 h-3.5 w-3.5" />
                    Alejar
                  </Button>
                  <span className="w-12 text-center text-xs font-mono font-medium text-foreground">
                    {Math.round(modalZoom * 100)}%
                  </span>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-8 text-xs px-2.5"
                    disabled={modalZoom >= 3.0}
                    onClick={() => setModalZoom((z) => Math.min(3.0, z + 0.15))}
                    title="Acercar"
                  >
                    <ZoomIn className="mr-1 h-3.5 w-3.5" />
                    Acercar
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-8 text-xs px-2"
                    onClick={() => setModalZoom(1.0)}
                    title="Restablecer a 100%"
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                  </Button>
                </div>

                {/* Orientation Toggle */}
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="flex items-center gap-1.5 h-8 text-xs px-2.5"
                  onClick={() => setDirection((prev) => (prev === "LR" ? "TB" : "LR"))}
                  title="Cambiar orientación de flujo"
                >
                  <Layout className="h-3.5 w-3.5" />
                  <span>
                    {direction === "LR" ? "Horizontal" : "Vertical"}
                  </span>
                </Button>

                {/* Close Button */}
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-8 text-xs px-2.5 border-destructive/20 text-destructive hover:bg-destructive/10 hover:text-destructive"
                  onClick={() => setIsModalOpen(false)}
                  title="Cerrar"
                >
                  <X className="mr-1 h-3.5 w-3.5" />
                  Cerrar
                </Button>
              </div>
            </div>

            {/* Scrollable Diagram Content */}
            <div className="flex-1 overflow-auto bg-muted/10 p-6 flex items-center justify-center">
              <div 
                className="border rounded-lg bg-card p-6 shadow-sm overflow-auto w-full h-full"
              >
                {/* Important style overrides to bypass Mermaid inline max-width/width limitations */}
                <div 
                  className="transition-all duration-150 [&_svg]:!max-w-none [&_svg]:!w-full [&_svg]:!h-auto block mx-auto"
                  style={{ 
                    width: `${modalZoom * 100}%`,
                  }}
                  dangerouslySetInnerHTML={{ __html: svg }}
                />
              </div>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}
