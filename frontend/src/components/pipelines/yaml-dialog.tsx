"use client";

// Free-form YAML editor for the active pipeline. Surfaces the serialised
// view (which the structured form computes via `docToYaml`) as an editable
// textarea so power users can hand-tweak fields the builder doesn't model.
// On save, the backend re-validates and writes verbatim; the page then
// reloads the saved YAML through `parseYamlToDoc` so both views resync.

import { useEffect, useState } from "react";
import { Save, X } from "lucide-react";

import { Button } from "@/components/ui/button";

export function PipelineYamlDialog({
  open,
  name,
  yamlText,
  canSave,
  onClose,
  onCopy,
  onSaveRaw,
}: {
  open: boolean;
  name: string;
  yamlText: string;
  canSave: boolean;
  onClose: () => void;
  onCopy: () => void;
  onSaveRaw: (raw: string) => Promise<void> | void;
}) {
  // Local editable buffer. Initialised from ``yamlText`` and re-synced when
  // the dialog reopens so the user always sees the latest serialised view as
  // a starting point. Edits stay local until the user clicks "Guardar".
  const [draft, setDraft] = useState(yamlText);
  useEffect(() => {
    if (open) setDraft(yamlText);
  }, [open, yamlText]);

  if (!open) return null;

  const dirty = draft !== yamlText;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-full max-w-4xl flex-col rounded-lg border border-border bg-card shadow-2xl">
        <header className="flex items-center justify-between border-b border-border px-6 py-4">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.08em] text-muted-foreground">
              YAML editable
            </div>
            <h3 className="text-lg font-semibold tracking-tight">{name}.yaml</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <X className="h-5 w-5" />
          </button>
        </header>

        <div className="flex-1 overflow-auto p-6">
          <textarea
            spellCheck={false}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="h-[60vh] w-full resize-none rounded-md border border-border bg-muted/20 p-4 font-mono text-xs leading-5 outline-none focus:border-ring"
          />
          <p className="mt-2 text-[11px] text-muted-foreground">
            Edita libremente el YAML aquí. El backend valida la sintaxis y la presencia
            de un campo <code>jobs</code> al guardar. Tras guardar, el editor visual se
            recarga; cualquier campo desconocido al builder se conservará en disco
            pero no se mostrará en los formularios.
          </p>
        </div>

        <footer className="flex justify-end gap-2 border-t border-border bg-muted/20 px-6 py-4">
          <Button type="button" variant="outline" size="sm" onClick={onCopy}>
            Copiar YAML
          </Button>
          <Button
            type="button"
            size="sm"
            disabled={!canSave || !dirty}
            title={!canSave ? "Guarda primero el pipeline desde el formulario" : undefined}
            onClick={() => void onSaveRaw(draft)}
          >
            <Save className="mr-1 h-3.5 w-3.5" /> Guardar YAML
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            Cerrar
          </Button>
        </footer>
      </div>
    </div>
  );
}
