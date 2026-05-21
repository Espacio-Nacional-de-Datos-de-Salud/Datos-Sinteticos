"use client";

// Generic "Historial" catalog table card. Each wizard-step page configures
// the column set (which is what varies most per kind) and provides a single
// `actionsCell` slot for the per-row buttons (cancel running / delete).
// Cleanup/purge buttons and the collapse toggle live in the card header and
// are uniform across kinds.

import { useState, type ReactNode } from "react";
import { Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { CollapseToggle } from "@/components/ui/collapse-toggle";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export type HistoryColumn<T> = {
  key: string;
  header: ReactNode;
  /** Width as a Tailwind percentage class fragment, e.g. "24%". */
  width: string;
  align?: "left" | "right";
  render: (item: T) => ReactNode;
};

export function HistoryCard<T>({
  title,
  description,
  items,
  isLoading,
  isError,
  errorMessage,
  emptyMessage,
  columns,
  actionsCell,
  actionsWidth = "10%",
  onCleanup,
  onPurge,
  isCleaning,
  isPurging,
  collapseLabel,
  onSelect,
  activeId,
  getRowId,
}: {
  title: string;
  description: string;
  items: T[];
  isLoading: boolean;
  isError: boolean;
  errorMessage: string;
  emptyMessage: string;
  columns: HistoryColumn<T>[];
  /** Right-aligned per-row actions (cancel running / delete). */
  actionsCell: (item: T) => ReactNode;
  actionsWidth?: string;
  onCleanup: () => void;
  onPurge: () => void;
  isCleaning: boolean;
  isPurging: boolean;
  /** Plural noun for the collapse toggle's aria-label, e.g. "generaciones". */
  collapseLabel: string;
  /** When provided, rows become clickable and load that run as active. */
  onSelect?: (id: string) => void;
  activeId?: string | null;
  /** Required when onSelect is provided. Returns the row's id. */
  getRowId?: (item: T) => string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between space-y-0">
        <div>
          <CardTitle className="text-base">{title}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </div>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={isCleaning || items.length === 0}
            onClick={onCleanup}
          >
            <Trash2 className="mr-2 h-3.5 w-3.5" />
            Limpiar sesiones incompletas
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={isPurging || items.length === 0}
            onClick={onPurge}
          >
            <Trash2 className="mr-2 h-3.5 w-3.5" />
            Limpiar todas las sesiones
          </Button>
          <CollapseToggle
            open={open}
            onToggle={() => setOpen((v) => !v)}
            ariaLabel={open ? `Contraer ${collapseLabel}` : `Expandir ${collapseLabel}`}
          />
        </div>
      </CardHeader>
      {open && (
        <CardContent>
          {isLoading && <Skeleton className="h-24 w-full" />}
          {isError && <p className="text-sm text-destructive">{errorMessage}</p>}
          {!isLoading && !isError && items.length === 0 && (
            <p className="text-sm text-muted-foreground">{emptyMessage}</p>
          )}
          {items.length > 0 && (
            // table-fixed + explicit widths keep the actions cell on screen
            // even when long string columns push everything else right.
            <Table className="table-fixed">
              <TableHeader>
                <TableRow>
                  {columns.map((col) => (
                    <TableHead
                      key={col.key}
                      className={col.align === "right" ? "text-right" : undefined}
                      style={{ width: col.width }}
                    >
                      {col.header}
                    </TableHead>
                  ))}
                  <TableHead style={{ width: actionsWidth }} />
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item, i) => {
                  const rowId = getRowId ? getRowId(item) : undefined;
                  const selectable = onSelect != null && rowId != null;
                  const isActive = selectable && rowId === activeId;
                  return (
                    <TableRow
                      key={i}
                      onClick={selectable ? () => onSelect!(rowId!) : undefined}
                      className={
                        selectable
                          ? "cursor-pointer " +
                            (isActive ? "bg-primary/5" : "hover:bg-accent")
                          : undefined
                      }
                    >
                      {columns.map((col) => (
                        <TableCell
                          key={col.key}
                          className={col.align === "right" ? "text-right" : undefined}
                        >
                          {col.render(item)}
                        </TableCell>
                      ))}
                      <TableCell
                        className="text-right"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <div className="flex items-center justify-end gap-1">
                          {actionsCell(item)}
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      )}
    </Card>
  );
}
