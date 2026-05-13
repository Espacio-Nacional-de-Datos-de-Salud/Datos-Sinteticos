"use client";

// "X actual" card shown above the history table on each wizard-step page.
// Renders the live status of the currently-active run (the one whose id is
// in localStorage). The shape is identical across pages — id, progress,
// inline rename — and each page slots in its own kind-specific metadata
// (tables, rows, accuracy, metrics, …) and action buttons (cancel +
// download/report).

import type { ReactNode } from "react";

import { EditableName } from "@/components/jobs/editable-name";
import { JobProgressPanel } from "@/components/jobs/job-progress";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { JobProgress } from "@/lib/api";

type ProgressLike = {
  status: string;
  progress?: JobProgress | null;
  timestamp?: string;
};

export function ActiveJobCard({
  id,
  title,
  description,
  isLoading,
  isError,
  errorMessage,
  active,
  activeName,
  existingNames,
  onRename,
  metadata,
  actions,
}: {
  id: string | null;
  title: string;
  description: string;
  isLoading: boolean;
  isError: boolean;
  errorMessage: string;
  /** The active artifact, when loaded. Drives the progress panel and slots. */
  active: ProgressLike | undefined;
  /** Display name shown in the EditableName field, when `active` is loaded. */
  activeName?: string;
  /** Existing names of all items, fed to EditableName to enforce uniqueness. */
  existingNames?: string[];
  /** Saves a new name for the active artifact. */
  onRename?: (name: string) => Promise<void>;
  /** Kind-specific metadata row (tables, rows, model, etc.). */
  metadata?: ReactNode;
  /** Kind-specific action buttons (cancel, download, …). */
  actions?: ReactNode;
}) {
  if (!id) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        <CardDescription>
          {description}
          <span className="ml-2 font-mono text-xs" suppressHydrationWarning>
            id: {id}
          </span>
        </CardDescription>
        {active && activeName && existingNames && onRename && (
          <EditableName
            name={activeName}
            existingNames={existingNames}
            onSave={onRename}
          />
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading && <Skeleton className="h-20 w-full" />}
        {isError && <p className="text-sm text-destructive">{errorMessage}</p>}
        {active && (
          <div className="space-y-3 text-sm">
            <JobProgressPanel
              status={active.status}
              progress={active.progress ?? null}
              timestamp={active.timestamp}
            />
            {metadata}
            {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
