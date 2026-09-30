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
import Script from "next/script";
import { Poppins, Geist_Mono } from "next/font/google";
import { ThemeProvider } from "@/lib/theme-provider";
import { QueryProvider } from "@/lib/query-provider";
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
      <head>
        <Script id="theme-init" strategy="beforeInteractive">{`try{var t=localStorage.getItem('theme')||'light';document.documentElement.classList.remove('light','dark');document.documentElement.classList.add(t==='system'?(window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'):t)}catch(e){}`}</Script>
      </head>
      <body className="h-full overflow-hidden bg-background text-foreground">
        <ThemeProvider defaultTheme="light">
          <QueryProvider>
            <div className="flex h-full flex-col">
              <Header />
              <div className="flex flex-1 overflow-hidden">
                <Sidebar />
                <main className="flex-1 overflow-hidden bg-background">{children}</main>
              </div>
            </div>
            <Toaster />
          </QueryProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
