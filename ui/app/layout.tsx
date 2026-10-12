import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Kawosz", template: "%s · Kawosz" },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    // Rozszerzenia przeglądarki (np. LanguageTool: data-lt-installed, Grammarly) dopisują atrybuty do <html>
    // i <body>, zanim React przejmie stronę. suppressHydrationWarning wycisza tylko różnice atrybutów tych dwóch
    // elementów, a nie zawartości panelu.
    <html lang="pl" suppressHydrationWarning>
      <body suppressHydrationWarning>
        <nav className="nawigacja" aria-label="Strony">
          <Link href="/">Jakość danych przychodu</Link>
          <Link href="/katalog">Katalog cech</Link>
        </nav>
        {children}
      </body>
    </html>
  );
}
