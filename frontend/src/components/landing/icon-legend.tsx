"use client";

import type { ReactNode } from "react";
import {
  BookOpen,
  ChevronsUpDown,
  Home,
  Moon,
  MoreVertical,
  PanelLeftClose,
  PanelLeftOpen,
  Sparkles,
  Sun,
  Trash2,
  X,
  Zap,
} from "lucide-react";

// UI legend surfaced from the instructions manual: a single reference for every
// global icon/control in the tool — where it lives and what it does. Mirrors the
// real components (Header, Sidebar, PageOutline, WizardBanner, ThemeToggle).

type LegendRow = {
  icon: ReactNode;
  where: string;
  what: string;
};

const ROWS: LegendRow[] = [
  {
    icon: (
      <span className="flex items-center gap-1.5 rounded-md bg-[#00215C] px-2 py-1 text-white">
        <Home className="h-4 w-4 text-[#FFDB00]" />
        <span className="text-[10px] font-semibold">Datos Sintéticos</span>
      </span>
    ),
    where: "En la esquina superior izquierda de la herramienta.",
    what: "Te devuelve a la página de inicio (esta).",
  },
  {
    icon: (
      <span className="flex items-center gap-1.5">
        <PanelLeftClose className="h-5 w-5" />
        <PanelLeftOpen className="h-5 w-5" />
      </span>
    ),
    where: "En la parte superior de los menús globales y de página, respectivamente.",
    what: "Colapsa el panel del menú hacia la izquierda.",
  },
  {
    icon: <ChevronsUpDown className="h-5 w-5" />,
    where: "En la parte superior del menú de página.",
    what: "Contrae las secciones del menú de página.",
  },
  {
    icon: <Sparkles className="h-5 w-5 text-violet-400" />,
    where: "En diversos puntos de la herramienta, tanto en el menú general y a nivel de página como dentro de las distintas secciones y subsecciones de cada página.",
    what: "Indica que las funcionalidades son de carácter avanzado y, por tanto, opcionales.",
  },
  {
    icon: (
      <span className="flex items-center gap-2">
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-[#FFDB00] text-[#00215C]">
          <Moon className="h-4 w-4" />
        </span>
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-[#FFDB00] text-[#00215C]">
          <Sun className="h-4 w-4" />
        </span>
      </span>
    ),
    where: "En la esquina superior derecha de la herramienta.",
    what: "Activa el modo noche / modo día.",
  },
  {
    icon: (
      <span className="flex h-7 w-7 items-center justify-center rounded-md bg-[#00215C] text-white">
        <MoreVertical className="h-4 w-4" />
      </span>
    ),
    where: "En la esquina superior derecha de la herramienta, al lado del modo noche / día.",
    what: "Menú de Panic Button y Borrar todo.",
  },
  {
    icon: (
      <span className="flex items-center gap-1.5 rounded-md bg-[#00215C] px-2.5 py-1.5 text-white">
        <Zap className="h-4 w-4" />
        <span className="text-[11px] font-semibold">Panic Button</span>
      </span>
    ),
    where: "Entrando en el menú de tres puntos de la esquina superior derecha de la herramienta.",
    what: "Panic Button: si crees que el motor de IA se ha quedado colgado, esto reiniciará el sistema.",
  },
  {
    icon: (
      <span className="flex items-center gap-1.5 rounded-md border border-red-400 bg-white px-2.5 py-1.5 text-red-500 dark:bg-card">
        <Trash2 className="h-4 w-4" />
        <span className="text-[11px] font-semibold">Borrar todo</span>
      </span>
    ),
    where: "Entrando en el menú de tres puntos de la esquina superior derecha de la herramienta.",
    what: "Elimina todas las ejecuciones.",
  },
  {
    icon: (
      <span className="flex items-center gap-1.5 rounded-md bg-[#FFDB00] px-2.5 py-1.5 text-[#00215C]">
        <BookOpen className="h-4 w-4" />
        <span className="text-[11px] font-semibold">Manual de instrucciones</span>
      </span>
    ),
    where: "En la esquina superior derecha de las páginas del Flujo de trabajo cuando el manual de instrucciones está cerrado.",
    what: "Abre el manual de instrucciones integrado en la herramienta.",
  },
  {
    icon: (
      <span className="flex items-center gap-1.5 rounded-md bg-[#00215C] px-2.5 py-1.5 text-white">
        <X className="h-4 w-4" />
        <span className="text-[11px] font-semibold">Cerrar</span>
      </span>
    ),
    where: "En la esquina superior derecha de las páginas del Flujo de trabajo cuando el manual de instrucciones está abierto.",
    what: "Cierra el manual de instrucciones integrado en la herramienta.",
  },
];

export function IconLegend() {
  return (
    <div className="overflow-hidden rounded-2xl border border-[#d8e3f4] dark:border-border">
      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="bg-[#dbe7fb] text-[#00215C] dark:bg-accent dark:text-white">
            <th className="w-40 px-4 py-2.5 text-center text-xs font-bold uppercase tracking-wide sm:w-52">
              Icono
            </th>
            <th className="px-4 py-2.5 text-xs font-bold uppercase tracking-wide">
              ¿Dónde lo encontrarás?
            </th>
            <th className="px-4 py-2.5 text-xs font-bold uppercase tracking-wide">
              ¿Qué hace / indica?
            </th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map((row, i) => (
            <tr
              key={i}
              className="border-t border-[#e3ebf7] bg-white align-top dark:border-border dark:bg-card"
            >
              <td className="px-4 py-3.5">
                <div className="flex items-center justify-center text-[#114da6] dark:text-[#FFDB00]">
                  {row.icon}
                </div>
              </td>
              <td className="px-4 py-3.5 text-xs leading-relaxed text-slate-600 dark:text-muted-foreground">
                {row.where}
              </td>
              <td className="px-4 py-3.5 text-xs leading-relaxed text-slate-600 dark:text-muted-foreground">
                {row.what}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
