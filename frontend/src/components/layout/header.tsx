"use client";

import Image from "next/image";
import Link from "next/link";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { ModeToggle } from "@/components/layout/mode-toggle";

export function Header() {
  // Placeholder until Keycloak wiring lands; until then, show a generic user.
  const username = "Usuario";
  const initial = username.charAt(0).toUpperCase();

  return (
    <header className="flex h-14 shrink-0 items-center justify-between bg-[#00215C] px-6 shadow-[0_2px_8px_rgba(0,0,0,0.2)]">
      <Link href="/" aria-label="Inicio" className="flex items-center gap-3.5">
        <Image
          src="/ends-assets/END_LOGO_BLANCO.svg"
          alt="Espacio Nacional de Datos de Salud"
          width={140}
          height={28}
          priority
          className="h-7 w-auto"
        />
        <span className="h-7 w-px bg-white/20" />
        <span className="text-[13px] font-semibold tracking-wide text-white/85">
          Datos Sintéticos
        </span>
        <span className="h-[3px] w-6 rounded-sm bg-[#FFDB00]" />
      </Link>

      <div className="flex items-center gap-3.5">
        <ModeToggle />
        <ThemeToggle />
        <div className="flex items-center gap-2.5 text-[13px] text-white/85">
          <div className="flex h-[30px] w-[30px] items-center justify-center rounded-full bg-[#114da6] text-[11px] font-bold text-white">
            {initial}
          </div>
          <span className="hidden sm:inline">{username}</span>
        </div>
      </div>
    </header>
  );
}
