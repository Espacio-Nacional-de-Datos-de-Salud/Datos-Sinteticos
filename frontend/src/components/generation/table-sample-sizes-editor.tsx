// Sample-size picker for the simulation step.
//
// Mostly AI only honors `sample_size` on the **mother** (root subject) table —
// the one without a context foreign key — and cascades every child's count from
// it. So there is exactly one row count the user can truly fix, and this editor
// lets them choose *which* one:
//
//   - The mother table (default): emitted as `{ [motherTable]: size }` via
//     `onChange`, which the backend reads as the subject target. The engine
//     honors it directly, so no oversampling is needed — unless rejection-
//     sampling rules exist, which discard rows and force overgeneration to
//     refill the count.
//   - One child table: emitted via `onFixedTargetChange` as `{ table, rows }`.
//     The backend then oversimulates the mother adaptively until that table
//     reaches the requested (rule-compliant) row count, and the mother and the
//     remaining tables float to whatever that requires.
//
// The two outputs are mutually exclusive — exactly one is non-null at any time.
//
// When oversampling can occur (child target, or mother + rejection rules) the
// editor also exposes the per-run sampling knobs (max retries / overgeneration
// factor). Defaults favor overgeneration over retries: each retry restarts the
// engine, which is far slower than drawing a bigger batch.

import { useEffect, useState } from "react";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Tooltip } from "@/components/ui/tooltip";
import { AdvancedBadge, ADVANCED_CARD_CLASS } from "@/components/ui/advanced-section";
import { cn } from "@/lib/utils";

export interface FixedTarget {
  table: string;
  rows: number;
}

interface TableSampleSizesEditorProps {
  originalSizes: Record<string, number>;
  subjectTables: string[];
  value: Record<string, number> | null;
  onChange: (sizes: Record<string, number> | null) => void;
  fixedTarget: FixedTarget | null;
  onFixedTargetChange: (target: FixedTarget | null) => void;
  hasRejectionRules: boolean;
  maxAttempts: string;
  onMaxAttemptsChange: (value: string) => void;
  overgenerateFactor: string;
  onOvergenerateFactorChange: (value: string) => void;
  /** When false (basic mode), the user can only fix the mother table's row
   *  count: the table picker and oversampling knobs are hidden. */
  allowFixedTarget?: boolean;
}

export function TableSampleSizesEditor({
  originalSizes,
  subjectTables,
  value,
  onChange,
  fixedTarget,
  onFixedTargetChange,
  hasRejectionRules,
  maxAttempts,
  onMaxAttemptsChange,
  overgenerateFactor,
  onOvergenerateFactorChange,
  allowFixedTarget = true,
}: TableSampleSizesEditorProps) {
  const tableNames = Object.keys(originalSizes);
  const subjectSet = new Set(subjectTables);
  // Fall back to all tables when the model predates the subject_tables field, so
  // the picker still works (just without knowing which are true subjects).
  const motherCandidates =
    subjectTables.length > 0 ? tableNames.filter((t) => subjectSet.has(t)) : tableNames;

  // Default mother = the subject with the most training rows (matches the
  // backend's multi-subject tie-break; unambiguous for the common single case).
  const defaultMother =
    [...motherCandidates].sort((a, b) => (originalSizes[b] ?? 0) - (originalSizes[a] ?? 0))[0] || "";

  // The mother is fixed by the schema — not user-selectable — so we just resolve
  // it once. A restored value may carry a size for it; otherwise default to the
  // mother's training row count.
  const seededMother = value ? Object.keys(value).find((t) => motherCandidates.includes(t)) : null;
  const motherTable = seededMother || defaultMother;
  // Children with a known training size: the tables whose count the user may
  // want to fix instead of the mother's.
  const childTables = tableNames.filter((t) => t !== motherTable && !subjectSet.has(t));

  // Initialised once per mount. The parent remounts this (via a key tied to the
  // selected model) when the model changes, so we never need to re-seed in an
  // effect — state resets cleanly on remount.
  const [fixedTable, setFixedTable] = useState<string>(() => fixedTarget?.table || motherTable);
  const [size, setSize] = useState<string>(() => {
    if (fixedTarget) return String(Math.max(1, fixedTarget.rows));
    const initialVal =
      seededMother && value ? value[seededMother] : (originalSizes[defaultMother] ?? 1);
    return String(Math.max(1, initialVal));
  });

  // Keep the request body in sync: exactly one of the two outputs is set.
  useEffect(() => {
    const n = Number.parseInt(size, 10);
    const clamped = !Number.isNaN(n) && n >= 1 ? n : 1;
    if (allowFixedTarget && fixedTable && fixedTable !== motherTable) {
      onChange(null);
      onFixedTargetChange({ table: fixedTable, rows: clamped });
    } else {
      onFixedTargetChange(null);
      onChange(motherTable ? { [motherTable]: clamped } : null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [motherTable, fixedTable, size, allowFixedTarget]);

  if (tableNames.length === 0 || !motherTable) return null;

  const hasChildren = allowFixedTarget && childTables.length > 0;
  const fixingChild = allowFixedTarget && fixedTable !== motherTable;
  // Oversampling only happens when the engine can't deliver the count directly:
  // a child target always needs it; a fixed mother only if rejection rules
  // discard rows. Otherwise the knobs are irrelevant and stay hidden.
  const showSamplingControls = allowFixedTarget && (fixingChild || hasRejectionRules);

  return (
    <div className="space-y-3 rounded-md border p-4">
      {/* Section title — kept inside the box and styled like CardTitle to match
          the card-titled subsections elsewhere on the page (e.g. the
          "Generación actual" card). */}
      <h3 className="font-heading text-base font-medium leading-snug">
        Configuración de volumen
      </h3>
      <div className="grid gap-3 md:grid-cols-2 md:items-end">
        {hasChildren && (
          <div className={cn("space-y-1 rounded-md p-2", ADVANCED_CARD_CLASS)}>
            <div className="flex items-center gap-2">
              <Label htmlFor="fixed-table-select" className="text-xs font-medium text-foreground">
                Tabla cuyo número de filas fijar
              </Label>
              <AdvancedBadge tooltip="Avanzado: fijar las filas de una tabla distinta de la maestra." />
              <Tooltip
                content="El motor solo permite fijar el tamaño de una tabla por generación. Si fijas la maestra, las hijas cascadean de ella. Si fijas una tabla hija, la maestra se sobresimulará lo necesario hasta alcanzar el número de filas pedido en la hija (filas que cumplan las reglas, si hay muestreo por rechazo), y el resto de tablas quedarán con el tamaño que resulte."
                side="right"
              />
            </div>
            <NativeSelect
              id="fixed-table-select"
              value={fixedTable}
              onValueChange={(table) => {
                setFixedTable(table);
                setSize(String(Math.max(1, originalSizes[table] ?? 1)));
              }}
              className="h-9 rounded-md px-3 font-mono text-xs"
            >
              <option value={motherTable}>{motherTable} (maestra)</option>
              {childTables.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </NativeSelect>
          </div>
        )}
        <div className="space-y-1">
          <Label htmlFor="sample-size-input" className="text-xs font-medium text-foreground">
            Filas de {fixedTable} a simular
          </Label>
          <Input
            id="sample-size-input"
            type="number"
            min={1}
            value={size}
            onChange={(e) => setSize(e.target.value)}
            onBlur={() => {
              const parsed = parseInt(size, 10);
              if (isNaN(parsed) || parsed < 1) {
                setSize("1");
              } else {
                setSize(String(parsed));
              }
            }}
            className="h-9"
            placeholder={`Ej: ${originalSizes[fixedTable]?.toLocaleString()}`}
          />
        </div>
      </div>
      {showSamplingControls && (
        <div className="grid gap-3 md:grid-cols-2 md:items-end">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Label
                htmlFor="overgenerate-factor-input"
                className="text-xs font-medium text-foreground"
              >
                Sobregeneración (×)
              </Label>
              <Tooltip
                content="Multiplicador aplicado a cada tirada para compensar las filas descartadas (y, fijando una hija, el déficit habitual de la cascada). Subir esto es mucho más barato que reintentar: cada reintento rearranca el motor, mientras que simular más filas de golpe apenas cuesta."
                side="right"
              />
            </div>
            <Input
              id="overgenerate-factor-input"
              type="number"
              min={1}
              max={20}
              step={0.5}
              value={overgenerateFactor}
              onChange={(e) => onOvergenerateFactorChange(e.target.value)}
              className="h-9"
            />
          </div>
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Label htmlFor="max-attempts-input" className="text-xs font-medium text-foreground">
                Reintentos máximos
              </Label>
              <Tooltip
                content="Número máximo de pasadas de generación si la primera no alcanza el objetivo. Cada reintento rearranca el motor (lento); antes de subir esto, sube la sobregeneración."
                side="right"
              />
            </div>
            <Input
              id="max-attempts-input"
              type="number"
              min={1}
              max={20}
              step={1}
              value={maxAttempts}
              onChange={(e) => onMaxAttemptsChange(e.target.value)}
              className="h-9"
            />
          </div>
        </div>
      )}
      {hasChildren && !fixingChild && (
        <div className="flex items-start gap-1.5 text-xs text-muted-foreground">
          <span>
            Las tablas hijas (con FK de contexto) cascadean su cantidad desde la maestra: su
            tamaño final no se puede garantizar en este modo.
            {hasRejectionRules
              ? " Hay reglas con muestreo por rechazo: se sobregenerará para reponer las filas descartadas y mantener el tamaño de la maestra."
              : " Sin reglas de muestreo por rechazo, el motor entrega el tamaño de la maestra exacto en una sola pasada."}
          </span>
          <Tooltip
            content="Mostly AI no admite un tamaño explícito por hija. Si necesitas un número exacto de filas en una tabla hija, selecciónala arriba: la maestra dejará de estar fijada y se sobresimulará hasta cumplir el objetivo de la hija."
            side="right"
          />
        </div>
      )}
      {fixingChild && (
        <div className="flex items-start gap-1.5 text-xs text-muted-foreground">
          <span>
            Se fijará el número de filas de <b>{fixedTable}</b>. La tabla maestra{" "}
            <b>{motherTable}</b> y el resto de tablas no quedan fijadas: la cascada suele
            producir menos filas hijas de las esperadas, así que la maestra se sobresimula
            siempre y, si hace falta, se reintenta hasta alcanzar el objetivo. Si hay reglas
            con muestreo por rechazo, solo cuentan las filas que las cumplen.
          </span>
        </div>
      )}
    </div>
  );
}
