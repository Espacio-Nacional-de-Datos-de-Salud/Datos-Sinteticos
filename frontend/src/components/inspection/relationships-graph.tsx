// ER diagram for detected relationships.
//
// Renders the autodetect schema (tables, PKs, FKs) as a Mermaid erDiagram so
// the user can see at a glance which tables connect to which. Mermaid is
// loaded lazily on the client because it touches the DOM and bloats the
// initial JS bundle if imported up-front.

"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { Autodetect, ForeignKey } from "@/lib/api";

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
): string {
  const lines: string[] = ["erDiagram"];
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

export function RelationshipsGraph({ autodetect }: { autodetect: Autodetect }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [svg, setSvg] = useState<string | null>(null);

  const diagram = useMemo(
    () =>
      buildErDiagram(
        autodetect.encoding_types ?? {},
        autodetect.relationships?.pks ?? {},
        autodetect.relationships?.fks ?? [],
      ),
    [autodetect],
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
        <div
          ref={containerRef}
          className="overflow-auto rounded-md border bg-card p-3"
          // Mermaid output is sanitised to inline SVG; safe to inject.
          dangerouslySetInnerHTML={{ __html: svg }}
        />
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
    </div>
  );
}
