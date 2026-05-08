// Root layout. Every page is rendered inside this chrome:
//
//   ┌────────────┬───────────────────────────────────┐
//   │  Sidebar   │  Header                           │
//   │ (wizard    │───────────────────────────────────│
//   │  steps)    │                                   │
//   │            │  <main> (this is `children`)      │
//   │            │                                   │
//   └────────────┴───────────────────────────────────┘
//
// Sidebar + Header are defined in src/components/layout/. They both read
// the current route to derive their active/breadcrumb state.

import type { Metadata } from "next";
import { Poppins, Geist_Mono } from "next/font/google";
import { ThemeProvider } from "next-themes";
import { QueryProvider } from "@/lib/query-provider";
import { ModeProvider } from "@/lib/mode";
import { Toaster } from "@/components/ui/sonner";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import "./globals.css";

const poppins = Poppins({
  variable: "--font-poppins",
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700", "800"],
});
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Datos sintéticos - ENDS",
  description: "Herramienta para el entrenamiento de modelos y generación de datos sintéticos tabulares médicos para el Espacio Nacional de Datos de Salud (ENDS).",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="es"
      className={`${poppins.variable} ${geistMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="h-full overflow-hidden bg-background text-foreground">
        <ThemeProvider attribute="class" defaultTheme="light" enableSystem>
          <QueryProvider>
            <ModeProvider>
              <div className="flex h-full flex-col">
                <Header />
                <div className="flex flex-1 overflow-hidden">
                  <Sidebar />
                  <main className="flex-1 overflow-hidden bg-background">{children}</main>
                </div>
              </div>
              <Toaster />
            </ModeProvider>
          </QueryProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
